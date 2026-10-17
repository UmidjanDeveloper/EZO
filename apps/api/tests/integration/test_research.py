import httpx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from ezo_api.db.models import ToolCall
from ezo_api.knowledge.fetch import SafeFetcher
from ezo_api.main import create_app
from ezo_api.tools.web_search import WebResult
from tests.conftest import make_settings
from tests.fakes import FakeProvider, FakeWebSearch
from tests.integration.helpers import stream_chat

ARTICLE = (
    "<html><head><title>Inflyatsiya 2026</title></head><body><article><h1>Inflyatsiya 2026</h1><p>"
    + "Rasmiy statistika ma'lumotiga ko'ra yillik inflyatsiya sentabrda 8,9 foizni tashkil etdi. "
    * 6
    + "</p></article></body></html>"
)


def _fetcher() -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=ARTICLE)

    async def resolve(host: str, port: int) -> list[str]:
        return ["93.184.216.34"]

    return SafeFetcher(transport=httpx.MockTransport(handler), resolver=resolve)


async def _client(
    database_url: str, providers: dict[str, FakeProvider], search: FakeWebSearch | None
):  # type: ignore[no-untyped-def]
    app = create_app(
        make_settings(database_url), providers=providers, web_search=search, fetcher=_fetcher()
    )
    return app, AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_research_agent_searches_ranks_reads_and_cites(database_url: str) -> None:
    planner_and_answer = FakeProvider(
        name="anthropic",
        replies=[
            '{"queries": ["Uzbekistan inflation September 2026", "inflyatsiya 2026"],'
            ' "recent": true}',
            "Inflyatsiya 8,9% [1]. Forumda boshqacha deyilgan [3].",
        ],
    )
    search = FakeWebSearch(
        results=[
            WebResult(
                "Reddit thread", "https://www.reddit.com/r/uz/1", "people say 12%", None, "fake"
            ),
            WebResult(
                "Statistika agentligi", "https://stat.uz/uz/inflation", "8.9%", "2026-10-05", "fake"
            ),
            WebResult(
                "Kun.uz",
                "https://kun.uz/news/2026/10/06/inflation",
                "inflyatsiya",
                "2026-10-06",
                "fake",
            ),
        ]
    )
    app, client = await _client(database_url, {"anthropic": planner_and_answer}, search)
    async with client:
        events = await stream_chat(
            client, message="Internetdan qidir: O'zbekistonda so'nggi inflyatsiya qancha?"
        )
        meta = events[0][1]
        assert meta["agent"] == "research"
        stages = [data["stage"] for name, data in events if name == "activity"]
        assert stages == ["searching", "reading"]  # web_search..., then web_fetch

        assert search.queries == ["Uzbekistan inflation September 2026", "inflyatsiya 2026"]
        system = planner_and_answer.requests[-1].system or ""
        # primary source first, read in full, with date and reliability
        assert "[1] Statistika agentligi" in system or "[1] Inflyatsiya 2026" in system
        assert "https://stat.uz/uz/inflation" in system and "(primary)" in system
        assert "8,9 foizni" in system  # fetched page text
        assert "state the date of each key fact" in system

        done = events[-1][1]["message"]
        assert done["content"] == "Inflyatsiya 8,9% [1]. Forumda boshqacha deyilgan [3]."
        cited = done["metadata"]["citations"]
        assert [c["n"] for c in cited] == [1, 3]
        assert cited[0]["url"] == "https://stat.uz/uz/inflation" and cited[0]["primary"] is True

        run = (await client.get(f"/api/agent-runs/{done['agent_run_id']}")).json()
        tools = [c["tool"] for c in run["tool_calls"]]
        assert tools[0] == "plan_queries"
        assert tools.count("web_search") == 2 and "web_fetch" in tools
    async with app.state.services.db.sessionmaker() as session:
        names = [t.tool_name for t in (await session.scalars(select(ToolCall))).all()]
        assert "web_search" in names and "web_fetch" in names
    await app.state.services.db.dispose()


async def test_research_without_web_search_is_honest(database_url: str) -> None:
    provider = FakeProvider(name="anthropic", replies=["not json", "Javob."])
    app, client = await _client(database_url, {"anthropic": provider}, None)
    async with client:
        await stream_chat(client, message="Search the web for the latest AI news")
        system = provider.requests[-1].system or ""
        assert "Web search is not configured" in system
    await app.state.services.db.dispose()


async def test_web_search_failure_is_reported(database_url: str) -> None:
    provider = FakeProvider(name="anthropic", replies=['{"queries": ["x"]}', "Javob."])
    app, client = await _client(
        database_url, {"anthropic": provider}, FakeWebSearch(error="quota exceeded")
    )
    async with client:
        events = await stream_chat(client, message="Internetdan qidir: yangi telefonlar narxi")
        assert "quota exceeded" in (provider.requests[-1].system or "")
        run = (
            await client.get(f"/api/agent-runs/{events[-1][1]['message']['agent_run_id']}")
        ).json()
        failed = [c for c in run["tool_calls"] if c["tool"] == "web_search"]
        assert failed and failed[0]["ok"] is False
    await app.state.services.db.dispose()
