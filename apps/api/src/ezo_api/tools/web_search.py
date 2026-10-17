"""Web search providers.

- TavilySearch: needs TAVILY_API_KEY (search API made for AI assistants).
- AnthropicWebSearch: uses Claude's built-in web search tool, so the
  Anthropic key alone is enough (web search must be enabled for the
  organisation in the Anthropic Console).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import anthropic
import httpx

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
# Models that support the dynamic-filtering web search tool version.
_WEB_SEARCH_V2_MODELS = (
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5-5",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
)
_SERVER_FALLBACK_MODELS = (
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
)


class WebSearchError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class WebResult:
    title: str
    url: str
    snippet: str
    published: str | None
    provider: str


class WebSearchProvider(ABC):
    name: str

    @abstractmethod
    async def search(
        self, query: str, max_results: int = 5, recent: bool = False
    ) -> list[WebResult]: ...


class TavilySearch(WebSearchProvider):
    name = "tavily"

    def __init__(self, api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._api_key = api_key
        self._transport = transport

    async def search(
        self, query: str, max_results: int = 5, recent: bool = False
    ) -> list[WebResult]:
        body: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
            "topic": "news" if recent else "general",
        }
        if recent:
            body["days"] = 30
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=20.0) as client:
                response = await client.post(
                    TAVILY_URL, json=body, headers={"Authorization": f"Bearer {self._api_key}"}
                )
        except httpx.HTTPError as exc:
            raise WebSearchError(f"Web search is unreachable ({type(exc).__name__}).") from exc
        if response.status_code in (401, 403):
            raise WebSearchError("The web search key (TAVILY_API_KEY) was rejected.")
        if response.status_code >= 400:
            raise WebSearchError(f"Web search failed with status {response.status_code}.")
        payload = response.json()
        return [
            WebResult(
                title=str(item.get("title") or item.get("url")),
                url=str(item["url"]),
                snippet=str(item.get("content") or "")[:1500],
                published=item.get("published_date"),
                provider=self.name,
            )
            for item in payload.get("results", [])
            if item.get("url")
        ]


class AnthropicWebSearch(WebSearchProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        self.model = model
        self._client: Any = client or anthropic.AsyncAnthropic(api_key=api_key, timeout=60.0)

    async def search(
        self, query: str, max_results: int = 5, recent: bool = False
    ) -> list[WebResult]:
        tool_type = (
            "web_search_20260209" if self.model in _WEB_SEARCH_V2_MODELS else "web_search_20250305"
        )
        prompt = (
            f"Search the web for: {query}\n"
            + ("Prefer the most recent sources. " if recent else "")
            + "Prefer official and primary sources. After searching, reply with one short sentence."
        )
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 2048,
            "tools": [{"type": tool_type, "name": "web_search", "max_uses": 2}],
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            if self.model in _SERVER_FALLBACK_MODELS:
                response = await self._client.beta.messages.create(
                    **params, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            else:
                response = await self._client.messages.create(**params)
        except anthropic.APIStatusError as exc:
            raise WebSearchError(
                f"Claude web search failed ({exc.status_code}): {exc.message}"
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise WebSearchError("Claude web search is unreachable.") from exc

        snippets: dict[str, str] = {}
        results: dict[str, WebResult] = {}
        for block in response.content:
            if block.type == "web_search_tool_result":
                content = block.content
                if not isinstance(content, list):  # an error object, e.g. max_uses_exceeded
                    code = getattr(content, "error_code", "unknown")
                    if not results:
                        raise WebSearchError(f"Claude web search returned an error: {code}")
                    continue
                for item in content:
                    if getattr(item, "type", "") == "web_search_result" and item.url not in results:
                        results[item.url] = WebResult(
                            title=item.title or item.url,
                            url=item.url,
                            snippet="",
                            published=getattr(item, "page_age", None),
                            provider=self.name,
                        )
            elif block.type == "text":
                for citation in getattr(block, "citations", None) or []:
                    if getattr(citation, "type", "") == "web_search_result_location":
                        snippets.setdefault(citation.url, citation.cited_text or "")
        ordered = [
            WebResult(r.title, r.url, snippets.get(r.url, ""), r.published, r.provider)
            for r in results.values()
        ]
        return ordered[:max_results]


def build_web_search(
    preference: str, tavily_key: str | None, anthropic_key: str | None, anthropic_model: str
) -> WebSearchProvider | None:
    if preference == "none":
        return None
    if preference in ("auto", "tavily") and tavily_key:
        return TavilySearch(tavily_key)
    if preference in ("auto", "anthropic") and anthropic_key:
        return AnthropicWebSearch(anthropic_key, anthropic_model)
    return None
