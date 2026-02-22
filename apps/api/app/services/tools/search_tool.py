from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from apps.api.app.core.config import get_settings

TOOL_NAME = "search"


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchTool(Protocol):
    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...


class TavilySearchTool:
    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        settings = get_settings()
        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY must be set to use search tool.")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.tavily_api_key,
                    "query": query,
                    "max_results": max_results,
                },
            )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results")
        if not isinstance(results, list):
            return []

        normalized: list[SearchResult] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            normalized.append(
                SearchResult(
                    title=str(item.get("title") or "").strip(),
                    url=str(item.get("url") or "").strip(),
                    snippet=str(item.get("content") or item.get("snippet") or "").strip(),
                )
            )
        return normalized


_search_tool: SearchTool = TavilySearchTool()


def get_search_tool() -> SearchTool:
    return _search_tool

