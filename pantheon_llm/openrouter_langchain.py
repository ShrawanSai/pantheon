from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Sequence

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI


@dataclass(frozen=True)
class LlmSpec:
    alias: str
    model_id: str
    tier: str


SUPPORTED_LLMS: dict[str, LlmSpec] = {
    "free": LlmSpec(alias="free", model_id="mistralai/mistral-small-3.1-24b-instruct:free", tier="free"),
    "llama": LlmSpec(alias="llama", model_id="meta-llama/llama-4-scout", tier="economy"),
    "qwen": LlmSpec(
        alias="qwen",
        model_id="qwen/qwen3-235b-a22b",
        tier="economy",
    ),
    "deepseek": LlmSpec(
        alias="deepseek",
        model_id="deepseek/deepseek-v3.1-terminus",
        tier="standard",
    ),
    "gpt_oss": LlmSpec(alias="gpt_oss", model_id="openai/gpt-oss-120b", tier="advanced"),
    "premium": LlmSpec(alias="premium", model_id="google/gemini-2.5-pro", tier="premium"),
}


def _load_env() -> tuple[str, str]:
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is missing. Set it in .env or environment.")
    return api_key, base_url


def get_chat_model(alias: str, temperature: float = 0.0, max_tokens: int | None = None) -> ChatOpenAI:
    if alias not in SUPPORTED_LLMS:
        supported = ", ".join(sorted(SUPPORTED_LLMS.keys()))
        raise ValueError(f"Unknown model alias '{alias}'. Supported: {supported}")

    api_key, base_url = _load_env()
    spec = SUPPORTED_LLMS[alias]

    kwargs = {
        "model": spec.model_id,
        "api_key": api_key,
        "base_url": base_url,
        "temperature": temperature,
        "extra_body": {
            "transforms": [],
        },
        "default_headers": {
            "HTTP-Referer": "https://pantheon.local",
            "X-Title": "Pantheon MVP",
        },
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    return ChatOpenAI(
        **kwargs,
    )


def invoke_text(alias: str, prompt: str) -> str:
    llm = get_chat_model(alias=alias)
    response = llm.invoke([HumanMessage(content=prompt)])
    return _extract_text(response)


async def ainvoke_text(alias: str, prompt: str) -> str:
    llm = get_chat_model(alias=alias)
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return _extract_text(response)


def invoke_messages(alias: str, messages: Sequence[BaseMessage]) -> str:
    llm = get_chat_model(alias=alias)
    response = llm.invoke(list(messages))
    return _extract_text(response)


async def ainvoke_messages(alias: str, messages: Sequence[BaseMessage]) -> str:
    llm = get_chat_model(alias=alias)
    response = await llm.ainvoke(list(messages))
    return _extract_text(response)


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
        return " ".join(c.strip() for c in chunks if c and c.strip()).strip()
    return str(content).strip()
