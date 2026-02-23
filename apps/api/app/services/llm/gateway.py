from __future__ import annotations

import asyncio
from dataclasses import dataclass
from math import ceil
from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from pantheon_llm.openrouter_langchain import SUPPORTED_LLMS, get_chat_model


MessageRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class GatewayMessage:
    role: MessageRole
    content: str


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


@dataclass(frozen=True)
class GatewayResponse:
    text: str
    provider_model: str
    usage: GatewayUsage


@dataclass(frozen=True)
class StreamingContext:
    chunks: AsyncIterator[str]
    usage_future: asyncio.Future[GatewayUsage]
    provider_model_future: asyncio.Future[str]


class LlmGateway(Protocol):
    async def generate(self, request: GatewayRequest) -> GatewayResponse: ...
    async def stream(self, request: GatewayRequest) -> StreamingContext: ...


def _estimate_tokens(text: str) -> int:
    return max(1, ceil(len(text) / 4 * 1.25))


def _extract_text(response: object) -> str:
    text_attr = getattr(response, "text", None)
    if isinstance(text_attr, str) and text_attr.strip():
        return text_attr.strip()

    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                chunks.append(item["text"])
            else:
                maybe_text = getattr(item, "text", None)
                if isinstance(maybe_text, str):
                    chunks.append(maybe_text)
        return " ".join(piece.strip() for piece in chunks if piece and piece.strip()).strip()
    return str(content).strip()


def _extract_delta(chunk: object) -> str:
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text_part = item.get("text")
                if isinstance(text_part, str):
                    parts.append(text_part)
            else:
                maybe_text = getattr(item, "text", None)
                if isinstance(maybe_text, str):
                    parts.append(maybe_text)
        return "".join(parts)
    return ""


def _to_langchain_messages(messages: list[GatewayMessage]) -> list[SystemMessage | HumanMessage | AIMessage]:
    converted: list[SystemMessage | HumanMessage | AIMessage] = []
    for message in messages:
        if message.role == "system":
            converted.append(SystemMessage(content=message.content))
        elif message.role == "assistant":
            converted.append(AIMessage(content=message.content))
        else:
            converted.append(HumanMessage(content=message.content))
    return converted


class OpenRouterLlmGateway:
    async def generate(self, request: GatewayRequest) -> GatewayResponse:
        if request.model_alias not in SUPPORTED_LLMS:
            supported = ", ".join(sorted(SUPPORTED_LLMS.keys()))
            raise ValueError(f"Unknown model alias '{request.model_alias}'. Supported: {supported}")

        llm = get_chat_model(alias=request.model_alias, max_tokens=request.max_output_tokens)
        response = await llm.ainvoke(_to_langchain_messages(request.messages))

        text = _extract_text(response)
        response_metadata = getattr(response, "response_metadata", {}) or {}
        usage_metadata = getattr(response, "usage_metadata", {}) or {}

        provider_model = str(response_metadata.get("model_name") or SUPPORTED_LLMS[request.model_alias].model_id)

        input_tokens = int(usage_metadata.get("input_tokens") or 0)
        output_tokens = int(usage_metadata.get("output_tokens") or 0)
        total_tokens = int(usage_metadata.get("total_tokens") or 0)
        input_details: dict[str, Any] = usage_metadata.get("input_token_details") or {}
        cached_tokens = int(input_details.get("cache_read") or input_details.get("cached_tokens") or 0)

        if input_tokens <= 0:
            input_tokens = sum(_estimate_tokens(message.content) for message in request.messages)
        if output_tokens <= 0:
            output_tokens = _estimate_tokens(text)
        if total_tokens <= 0:
            total_tokens = input_tokens + output_tokens

        input_tokens_fresh = max(input_tokens - cached_tokens, 0)
        input_tokens_cached = max(cached_tokens, 0)

        return GatewayResponse(
            text=text,
            provider_model=provider_model,
            usage=GatewayUsage(
                input_tokens_fresh=input_tokens_fresh,
                input_tokens_cached=input_tokens_cached,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            ),
        )

    async def stream(self, request: GatewayRequest) -> StreamingContext:
        if request.model_alias not in SUPPORTED_LLMS:
            supported = ", ".join(sorted(SUPPORTED_LLMS.keys()))
            raise ValueError(f"Unknown model alias '{request.model_alias}'. Supported: {supported}")

        llm = get_chat_model(alias=request.model_alias, max_tokens=request.max_output_tokens)
        usage_future: asyncio.Future[GatewayUsage] = asyncio.get_running_loop().create_future()
        provider_model_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()

        async def _iter_chunks() -> AsyncIterator[str]:
            output_parts: list[str] = []
            input_tokens = 0
            output_tokens = 0
            total_tokens = 0
            cached_tokens = 0
            provider_model = SUPPORTED_LLMS[request.model_alias].model_id
            try:
                async for chunk in llm.astream(_to_langchain_messages(request.messages)):
                    response_metadata = getattr(chunk, "response_metadata", {}) or {}
                    usage_metadata = getattr(chunk, "usage_metadata", {}) or {}
                    if response_metadata.get("model_name"):
                        provider_model = str(response_metadata["model_name"])
                    if usage_metadata:
                        input_tokens = int(usage_metadata.get("input_tokens") or input_tokens or 0)
                        output_tokens = int(usage_metadata.get("output_tokens") or output_tokens or 0)
                        total_tokens = int(usage_metadata.get("total_tokens") or total_tokens or 0)
                        input_details: dict[str, Any] = usage_metadata.get("input_token_details") or {}
                        cached_tokens = int(
                            input_details.get("cache_read") or input_details.get("cached_tokens") or cached_tokens or 0
                        )

                    delta = _extract_delta(chunk)
                    if delta:
                        output_parts.append(delta)
                        yield delta

                assembled_text = "".join(output_parts)
                if input_tokens <= 0:
                    input_tokens = sum(_estimate_tokens(message.content) for message in request.messages)
                if output_tokens <= 0:
                    output_tokens = _estimate_tokens(assembled_text)
                if total_tokens <= 0:
                    total_tokens = input_tokens + output_tokens

                usage = GatewayUsage(
                    input_tokens_fresh=max(input_tokens - cached_tokens, 0),
                    input_tokens_cached=max(cached_tokens, 0),
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                )
                if not usage_future.done():
                    usage_future.set_result(usage)
                if not provider_model_future.done():
                    provider_model_future.set_result(provider_model)
            except Exception as exc:
                if not usage_future.done():
                    usage_future.set_exception(exc)
                if not provider_model_future.done():
                    provider_model_future.set_exception(exc)
                raise

        return StreamingContext(
            chunks=_iter_chunks(),
            usage_future=usage_future,
            provider_model_future=provider_model_future,
        )


_llm_gateway: LlmGateway = OpenRouterLlmGateway()


def get_llm_gateway() -> LlmGateway:
    return _llm_gateway
