import json
from types import SimpleNamespace as NS
from typing import Any

import httpx
import pytest

from ezo_api.tools.reliability import score_url
from ezo_api.tools.web_search import (
    AnthropicWebSearch,
    TavilySearch,
    WebSearchError,
    build_web_search,
)


async def test_tavily_maps_results_and_sends_key() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Stat",
                        "url": "https://stat.uz/a",
                        "content": "9%",
                        "published_date": "2026-10-01",
                    }
                ]
            },
        )

    search = TavilySearch("tvly-key", transport=httpx.MockTransport(handler))
    results = await search.search("inflyatsiya", 3, recent=True)
    assert seen["auth"] == "Bearer tvly-key"
    assert seen["body"]["topic"] == "news" and seen["body"]["max_results"] == 3
    assert results[0].url == "https://stat.uz/a" and results[0].published == "2026-10-01"


async def test_tavily_rejected_key_is_explained() -> None:
    search = TavilySearch("bad", transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(WebSearchError, match="TAVILY_API_KEY"):
        await search.search("x")


class _FakeAnthropic:
    def __init__(self, content: list[Any]) -> None:
        self.calls: list[dict[str, Any]] = []
        outer = self

        async def create(**params: Any) -> Any:
            outer.calls.append(params)
            return NS(content=content)

        self.messages = NS(create=create)
        self.beta = NS(messages=NS(create=create))


async def test_anthropic_web_search_reads_result_blocks_and_citations() -> None:
    content = [
        NS(type="server_tool_use"),
        NS(
            type="web_search_tool_result",
            content=[
                NS(
                    type="web_search_result",
                    url="https://lex.uz/docs/1",
                    title="Qonun",
                    page_age="2026-09-30",
                ),
                NS(
                    type="web_search_result",
                    url="https://kun.uz/n",
                    title="Yangilik",
                    page_age=None,
                ),
            ],
        ),
        NS(
            type="text",
            citations=[
                NS(
                    type="web_search_result_location",
                    url="https://lex.uz/docs/1",
                    cited_text="Ushbu qonun kuchga kiradi",
                )
            ],
        ),
    ]
    client = _FakeAnthropic(content)
    search = AnthropicWebSearch("key", "claude-sonnet-5-5", client=client)
    results = await search.search("yangi qonun", 5)
    assert [r.url for r in results] == ["https://lex.uz/docs/1", "https://kun.uz/n"]
    assert results[0].snippet == "Ushbu qonun kuchga kiradi"
    params = client.calls[0]
    assert params["tools"][0]["type"] == "web_search_20260209"
    assert params["fallbacks"] == "default"


async def test_anthropic_web_search_error_object() -> None:
    client = _FakeAnthropic(
        [NS(type="web_search_tool_result", content=NS(error_code="unavailable"))]
    )
    with pytest.raises(WebSearchError, match="unavailable"):
        await AnthropicWebSearch("key", "claude-haiku-5-5", client=client).search("x")
    assert client.calls[0]["tools"][0]["type"] == "web_search_20250305"


def test_provider_selection() -> None:
    assert build_web_search("auto", "t", "a", "m").name == "tavily"  # type: ignore[union-attr]
    assert build_web_search("auto", None, "a", "m").name == "anthropic"  # type: ignore[union-attr]
    assert build_web_search("auto", None, None, "m") is None
    assert build_web_search("none", "t", "a", "m") is None


@pytest.mark.parametrize(
    ("url", "primary", "minimum"),
    [
        ("https://lex.uz/docs/123", True, 0.9),
        ("https://www.gov.uz/uz/news", True, 0.9),
        ("https://mf.uz.gov.uz/x", True, 0.9),
        ("https://arxiv.org/abs/1", True, 0.8),
        ("https://kun.uz/news/1", False, 0.6),
        ("https://en.wikipedia.org/wiki/X", False, 0.6),
    ],
)
def test_reliability_tiers(url: str, primary: bool, minimum: float) -> None:
    score, is_primary, _ = score_url(url)
    assert is_primary is primary and score >= minimum


def test_social_media_is_low() -> None:
    assert score_url("https://www.reddit.com/r/x")[0] < 0.5
    assert score_url("https://t.me/channel")[0] < 0.5
