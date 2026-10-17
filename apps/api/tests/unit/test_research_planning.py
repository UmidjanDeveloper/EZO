from ezo_api.agents.research import parse_plan, rank_web_sources
from ezo_api.knowledge.retrieval.sources import SourceRef


def test_parse_plan_from_model_json() -> None:
    plan = parse_plan(
        'Sure: {"queries": ["Uzbekistan inflation 2026", "inflyatsiya"], "recent": true}', "q"
    )
    assert plan.queries == ["Uzbekistan inflation 2026", "inflyatsiya"] and plan.recent
    assert plan.planned_by_model


def test_parse_plan_fallback_on_garbage() -> None:
    plan = parse_plan("I cannot do JSON", "bugungi yangiliklar")
    assert plan.queries == ["bugungi yangiliklar"]
    assert plan.recent  # "bugun" signals current information
    assert not plan.planned_by_model


def test_rank_prefers_primary_and_deduplicates() -> None:
    def src(
        url: str, reliability: float, primary: bool = False, date: str | None = None
    ) -> SourceRef:
        return SourceRef(
            kind="web",
            title=url,
            excerpt="x",
            source_name="t",
            url=url,
            reliability=reliability,
            primary=primary,
            date=date,
        )

    ranked = rank_web_sources(
        [
            src("https://reddit.com/r/a", 0.35),
            src("https://kun.uz/a", 0.7, date="2026-10-16"),
            src("https://www.lex.uz/docs/1/", 0.95, primary=True),
            src("https://lex.uz/docs/1", 0.95, primary=True),  # duplicate
        ],
        recent=True,
    )
    assert [s.url for s in ranked] == [
        "https://www.lex.uz/docs/1/",
        "https://kun.uz/a",
        "https://reddit.com/r/a",
    ]
