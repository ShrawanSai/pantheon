from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol, Type

from pydantic import BaseModel
from openai import AsyncOpenAI

from pantheon_llm.openrouter_langchain import SUPPORTED_LLMS

_LOGGER = logging.getLogger(__name__)

MessageRole = Literal["system", "user", "assistant", "tool"]

@dataclass(frozen=True)
class GatewayMessage:
    role: MessageRole
    content: str
    tool_calls: list[Any] | None = None
    tool_call_id: str | None = None

@dataclass(frozen=True)
class GatewayUsage:
    input_tokens_fresh: int
    input_tokens_cached: int
    output_tokens: int
    total_tokens: int

@dataclass(frozen=True)
class GatewayRequest:
    model_alias: str
    messages: list[GatewayMessage]
    max_output_tokens: int
    allowed_tools: tuple[str, ...] = ()
    response_schema: Type[BaseModel] | None = None
    stop_sequences: list[str] | None = None

@dataclass(frozen=True)
class GatewayResponse:
    text: str
    provider_model: str
    usage: GatewayUsage
    tool_calls: list[Any] | None = None
    thinking: str | None = None
    raw_json: str | None = None

@dataclass(frozen=True)
class StreamingContext:
    chunks: AsyncIterator[str]
    usage_future: asyncio.Future[GatewayUsage]
    provider_model_future: asyncio.Future[str]

class LlmGateway(Protocol):
    async def generate(self, request: GatewayRequest) -> GatewayResponse: ...
    async def stream(self, request: GatewayRequest) -> StreamingContext: ...

def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 4 * 1.25))

def _build_openai_messages(messages: list[GatewayMessage]) -> list[dict[str, Any]]:
    output = []
    for msg in messages:
        if msg.role == "tool":
            output.append({"role": "tool", "content": msg.content, "tool_call_id": msg.tool_call_id})
        elif msg.role == "assistant" and msg.tool_calls:
            output.append({"role": "assistant", "content": msg.content or "", "tool_calls": msg.tool_calls})
        else:
            output.append({"role": msg.role, "content": msg.content})
    return output

_TOOL_DEFINITIONS = {
    "search": {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search the web for current information and recent facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."}
                },
                "required": ["query"],
            },
        },
    },
    "file_read": {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read an uploaded file by file id and return parsed content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {"type": "string", "description": "The ID of the file to read."}
                },
                "required": ["file_id"],
            },
        },
    }
}

class OpenAICompatibleGateway:
    def __init__(self):
        api_key = os.getenv("OPENROUTER_API_KEY", "dummy_key")
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def generate(self, request: GatewayRequest) -> GatewayResponse:
        model_id = request.model_alias
        if request.model_alias in SUPPORTED_LLMS:
            model_id = SUPPORTED_LLMS[request.model_alias].model_id

        tools = [_TOOL_DEFINITIONS[t] for t in request.allowed_tools if t in _TOOL_DEFINITIONS] or None

        # Build response_format for structured output
        extra_kwargs: dict[str, Any] = {}
        if request.response_schema and not tools:
            schema = request.response_schema.model_json_schema()
            extra_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.response_schema.__name__,
                    "strict": True,
                    "schema": schema,
                },
            }
        
        if request.stop_sequences:
            extra_kwargs["stop"] = request.stop_sequences

        response = await self._client.chat.completions.create(
            model=model_id,
            messages=_build_openai_messages(request.messages),
            max_tokens=request.max_output_tokens,
            tools=tools,  # type: ignore
            **extra_kwargs,
        )

        choice = response.choices[0]
        text = choice.message.content or ""
        tool_calls = choice.message.tool_calls
        
        provider_model = response.model or model_id
        
        usage = response.usage
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        
        # openrouter / openai cache tracking
        prompt_details = getattr(usage, "prompt_tokens_details", None)
        cached_tokens = 0
        if prompt_details:
            if isinstance(prompt_details, dict):
                cached_tokens = prompt_details.get("cached_tokens", 0)
            else:
                cached_tokens = getattr(prompt_details, "cached_tokens", 0)
        
        if input_tokens == 0:
            input_tokens = sum(_estimate_tokens(m.content) for m in request.messages if m.content)
        # If structured output was requested, parse the JSON to extract fields
        thinking = None
        raw_json = None
        if request.response_schema and not tools:
            raw_json = text
            try:
                parsed = json.loads(text)
                text = parsed.get("response", text)
                thinking = parsed.get("thinking", "")
                _LOGGER.debug("Structured output parsed. thinking=%s", thinking[:100] if thinking else "")
            except (json.JSONDecodeError, KeyError) as exc:
                _LOGGER.warning("Failed to parse structured output, using raw text: %s", exc)

        return GatewayResponse(
            text=text,
            provider_model=provider_model,
            usage=GatewayUsage(
                input_tokens_fresh=max(0, input_tokens - cached_tokens),
                input_tokens_cached=cached_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            tool_calls=[tc.model_dump() for tc in tool_calls] if tool_calls else None,
            thinking=thinking,
            raw_json=raw_json,
        )

    async def stream(self, request: GatewayRequest) -> StreamingContext:
        model_id = request.model_alias
        if request.model_alias in SUPPORTED_LLMS:
            model_id = SUPPORTED_LLMS[request.model_alias].model_id

        usage_future: asyncio.Future[GatewayUsage] = asyncio.get_running_loop().create_future()
        provider_model_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()

        async def _iter_chunks() -> AsyncIterator[str]:
            extra_kwargs: dict[str, Any] = {}
            if request.stop_sequences:
                extra_kwargs["stop"] = request.stop_sequences
                
            try:
                stream_response = await self._client.chat.completions.create(
                    model=model_id,
                    messages=_build_openai_messages(request.messages),
                    max_tokens=request.max_output_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                    **extra_kwargs
                )
                
                output_parts = []
                final_usage = None
                provider_model = model_id
                
                async for chunk in stream_response:
                    if chunk.model:
                        provider_model = chunk.model
                        
                    if len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta.content or ""
                        if delta:
                            output_parts.append(delta)
                            yield delta
                            
                    if getattr(chunk, "usage", None):
                        final_usage = chunk.usage

                if not provider_model_future.done():
                    provider_model_future.set_result(provider_model)

                if final_usage:
                    input_tokens = getattr(final_usage, "prompt_tokens", 0) or 0
                    output_tokens = getattr(final_usage, "completion_tokens", 0) or 0
                    prompt_details = getattr(final_usage, "prompt_tokens_details", None)
                    cached_tokens = 0
                    if prompt_details:
                        if isinstance(prompt_details, dict):
                            cached_tokens = prompt_details.get("cached_tokens", 0)
                        else:
                            cached_tokens = getattr(prompt_details, "cached_tokens", 0)

                    if input_tokens == 0:
                        input_tokens = sum(_estimate_tokens(m.content) for m in request.messages if m.content)
                else:
                    text = "".join(output_parts)
                    input_tokens = sum(_estimate_tokens(m.content) for m in request.messages if m.content)
                    output_tokens = _estimate_tokens(text)
                    cached_tokens = 0

                usage_obj = GatewayUsage(
                    input_tokens_fresh=max(0, input_tokens - cached_tokens),
                    input_tokens_cached=cached_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                )
                if not usage_future.done():
                    usage_future.set_result(usage_obj)
                    
            except Exception as e:
                if not usage_future.done():
                    usage_future.set_exception(e)
                if not provider_model_future.done():
                    provider_model_future.set_exception(e)
                raise e

        return StreamingContext(
            chunks=_iter_chunks(),
            usage_future=usage_future,
            provider_model_future=provider_model_future
        )

_llm_gateway: LlmGateway = OpenAICompatibleGateway()

def get_llm_gateway() -> LlmGateway:
    return _llm_gateway
