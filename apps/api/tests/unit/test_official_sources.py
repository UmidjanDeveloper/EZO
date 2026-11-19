"""Official-source framework without a database: legal text parsing, scripts, the LEX.UZ
connector and the rule-following HTTP client (mocked network only)."""

from __future__ import annotations

import time
from datetime import date

import httpx
import pytest

from ezo_api.knowledge.fetch import FetchedPage
from ezo_api.official.base import (
    AccessRestrictedError,
    BudgetExhaustedError,
    DocumentParseError,
    DocumentRef,
    RateLimitedError,
    RobotsUnavailableError,
    SourceNotEnabledError,
    TemporaryFetchError,
    UnsupportedSourceError,
)
from ezo_api.official.http import OfficialHttpClient
from ezo_api.official.legal_text import (
    cyrl_to_latn,
    explicit_status,
    latn_to_cyrl,
    mark_articles,
    parse_title,
    query_variants,
    script_of,
    status_from_label,
)
from ezo_api.official.lexuz import POLICY, LexUzConnector
from ezo_api.official.registry import all_policies, get_connector
from tests.official_fixtures import LRU_682, RUSSIAN, UZ_CYRILLIC, UZ_LATIN, FakeSite, Sleeps, html

# --- legal text ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "number", "kind", "rest"),
    [
        (
            "LRU-682-сон 20.04.2021. On normative legal acts",
            "LRU-682",
            "law",
            "On normative legal acts",
        ),
        (
            "ЎРҚ-682-сон 20.04.2021. Норматив-ҳуқуқий ҳужжатлар тўғрисида",
            "ЎРҚ-682",
            "law",
            "Норматив-ҳуқуқий ҳужжатлар тўғрисида",
        ),
        (
            "O‘RQ-682-son 20.04.2021. Normativ-huquqiy hujjatlar toʻgʻrisida",
            "O‘RQ-682",
            "law",
            "Normativ-huquqiy hujjatlar toʻgʻrisida",
        ),
        (
            "ЗРУ-682 от 20.04.2021 г. О нормативно-правовых актах",
            "ЗРУ-682",
            "law",
            "О нормативно-правовых актах",
        ),
    ],
)
def test_parse_title_in_every_script(title: str, number: str, kind: str, rest: str) -> None:
    info = parse_title(title)
    assert (info.number, info.document_type, info.title) == (number, kind, rest)
    assert info.adopted_on == date(2021, 4, 20) and info.authority == "Oliy Majlis"


def test_parse_title_types_and_missing_parts() -> None:
    decree = parse_title("PF-60 28.01.2022. Strategiya toʻgʻrisida")
    assert decree.document_type == "presidential_decree" and decree.number == "PF-60"
    cabinet = parse_title("ВМҚ-15-сон 10.01.2023. Низом")
    assert cabinet.document_type == "cabinet_resolution"
    plain = parse_title("Oʻzbekiston Respublikasining Mehnat kodeksi")
    assert plain.number is None and plain.adopted_on is None and plain.document_type is None
    assert parse_title("ЎРҚ-1-сон 31.02.2021. X").adopted_on is None  # impossible date: none


def test_status_comes_only_from_an_explicit_label() -> None:
    assert status_from_label("Amaldagi") == "in_force"
    assert status_from_label("Ўз кучини йўқотган") == "repealed"
    assert status_from_label("Утратил силу") == "repealed"
    assert status_from_label("something else") is None
    assert explicit_status("Holati: Kuchini yoʻqotgan\n1-modda.") == "repealed"
    assert explicit_status("Статус: Действующий") == "in_force"
    # A law repealing ANOTHER act says nothing about its own status.
    body = "5-modda. Quyidagi qaror oʻz kuchini yoʻqotgan deb hisoblansin."
    assert explicit_status(body) is None


def test_scripts_transliteration_and_query_variants() -> None:
    assert script_of("Норматив-ҳуқуқий ҳужжатлар") == "cyrl"
    assert script_of("Normativ-huquqiy hujjatlar") == "latn"
    assert cyrl_to_latn("Меҳнат кодекси, ер, Ўзбекистон") == "Mehnat kodeksi, yer, Oʻzbekiston"
    assert cyrl_to_latn("шаҳар, чегара") == "shahar, chegara"
    assert latn_to_cyrl("mehnat kodeksi") == "меҳнат кодекси"
    assert query_variants("mehnat taʼtili") == ["mehnat taʼtili", "меҳнат таʼтили"]
    assert query_variants("меҳнат") == ["меҳнат", "mehnat"]


def test_articles_become_sections() -> None:
    marked = mark_articles("1-modda. Maqsad\nmatn\nСтатья 2. Цель\nтекст\n12-модда. Ҳуқуқ")
    assert marked.splitlines()[0] == "## 1-modda. Maqsad"
    assert "## Статья 2. Цель" in marked and "## 12-модда. Ҳуқуқ" in marked


# --- LEX.UZ connector --------------------------------------------------------------------


def test_lexuz_ids_and_urls() -> None:
    connector = LexUzConnector()
    assert connector.validate_id(" 5695915 ") == "5695915"
    assert connector.validate_id("-6445145") == "6445145"  # as some corpora export it
    for bad in ("../etc/passwd", "abc", "123?x=1", "", "1" * 11):
        with pytest.raises(UnsupportedSourceError):
            connector.validate_id(bad)
    assert connector.document_url(DocumentRef(LRU_682, "uz")) == "https://lex.uz/docs/5695915"
    assert connector.document_url(DocumentRef(LRU_682, "ru")) == "https://lex.uz/ru/docs/5695915"
    with pytest.raises(UnsupportedSourceError):
        connector.document_url(DocumentRef(LRU_682, "en"))
    with pytest.raises(UnsupportedSourceError, match="no verified change feed"):
        connector.changed_since()


def _page(body: str, url: str = "https://lex.uz/docs/5695915") -> FetchedPage:
    return FetchedPage(url, url, "text/html", body.encode(), time.time())


@pytest.mark.parametrize(
    ("page", "language", "script", "number", "first_article"),
    [
        (UZ_LATIN, "uz", "latn", "O‘RQ-682", "## 1-modda. Ushbu Qonunning maqsadi"),
        (UZ_CYRILLIC, "uz", "cyrl", "ЎРҚ-682", "## 1-модда. Ушбу Қонуннинг мақсади"),
        (RUSSIAN, "ru", "cyrl", "ЗРУ-682", "## Статья 1. Цель настоящего Закона"),
    ],
)
def test_lexuz_parses_documents_in_three_scripts(
    page: str, language: str, script: str, number: str, first_article: str
) -> None:
    parsed = LexUzConnector().parse(_page(page), DocumentRef(LRU_682, language))
    assert parsed.document_number == number and parsed.adopted_on == date(2021, 4, 20)
    assert parsed.script == script and parsed.document_type == "law"
    assert first_article in parsed.text
    assert "Bosh sahifa" not in parsed.text  # navigation is not document text
    assert parsed.status == "unknown" and parsed.status_source == "unverified"
    assert any("does not assume" in w for w in parsed.warnings)


def test_lexuz_rejects_pages_without_a_document() -> None:
    with pytest.raises(DocumentParseError):
        LexUzConnector().parse(
            _page("<html><title>LEX.UZ</title><body>Kirish</body></html>"), DocumentRef("1", "uz")
        )


# --- HTTP rules ---------------------------------------------------------------------------


def _client(site: FakeSite, **kwargs: object) -> tuple[OfficialHttpClient, Sleeps]:
    sleeps = Sleeps()
    options: dict[str, object] = {"min_interval": 5.0, "max_requests": 10, **kwargs}
    return OfficialHttpClient(site.fetcher(), POLICY, sleep=sleeps, **options), sleeps  # type: ignore[arg-type]


async def test_client_obeys_robots_and_paces_requests() -> None:
    site = FakeSite(
        robots=httpx.Response(200, text="User-agent: *\nDisallow: /private/\nCrawl-delay: 7\n")
    )
    site.routes["/docs/1"] = html(UZ_LATIN)
    site.routes["/docs/2"] = html(UZ_LATIN)
    clock = iter([0.0, 0.0, 1.0, 1.0, 2.0, 2.0, 3.0, 3.0])
    client, sleeps = _client(site, clock=lambda: next(clock))
    await client.get("https://lex.uz/docs/1")
    await client.get("https://lex.uz/docs/2")
    assert site.log == ["/robots.txt", "/docs/1", "/docs/2"]
    assert client.min_interval == 7.0  # Crawl-delay raised the floor
    assert sleeps.calls and all(wait > 5.0 for wait in sleeps.calls)
    with pytest.raises(AccessRestrictedError, match=r"robots\.txt"):
        await client.get("https://lex.uz/private/x")
    assert "/private/x" not in site.log  # never requested


async def test_client_fails_closed_when_robots_is_unreadable() -> None:
    site = FakeSite(robots=httpx.Response(503))
    site.routes["/docs/1"] = html(UZ_LATIN)
    client, _ = _client(site)
    with pytest.raises(RobotsUnavailableError):
        await client.get("https://lex.uz/docs/1")
    assert site.log == ["/robots.txt"]


async def test_client_never_works_around_refusals() -> None:
    site = FakeSite()
    site.routes["/docs/1"] = httpx.Response(403)
    site.routes["/docs/2"] = httpx.Response(429, headers={"retry-after": "30"})
    site.routes["/docs/3"] = httpx.Response(502)
    client, _ = _client(site)
    with pytest.raises(AccessRestrictedError, match="403"):
        await client.get("https://lex.uz/docs/1")
    with pytest.raises(RateLimitedError) as limited:
        await client.get("https://lex.uz/docs/2")
    assert limited.value.retry_after == 30.0
    with pytest.raises(TemporaryFetchError):
        await client.get("https://lex.uz/docs/3")
    with pytest.raises(TemporaryFetchError, match="no document"):
        await client.get("https://lex.uz/docs/404")


async def test_client_limits_hosts_and_budget() -> None:
    site = FakeSite()
    site.routes["/docs/1"] = html(UZ_LATIN)
    client, _ = _client(site, max_requests=2)
    for url in (
        "http://lex.uz/docs/1",
        "https://evil.example/docs/1",
        "https://lex.uz.evil.example/x",
    ):
        with pytest.raises(UnsupportedSourceError):
            await client.get(url)
    await client.get("https://lex.uz/docs/1")  # robots.txt + document = 2 requests
    with pytest.raises(BudgetExhaustedError):
        await client.get("https://lex.uz/docs/1")


async def test_network_failures_are_temporary() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ConnectError("connection refused")

    site = FakeSite()
    site.handler = broken  # type: ignore[method-assign]
    client, _ = _client(site)
    with pytest.raises(TemporaryFetchError):
        await client.get("https://lex.uz/docs/1")


# --- registry ------------------------------------------------------------------------------


def test_only_verified_and_enabled_sources_can_be_used() -> None:
    keys = [p.key for p in all_policies()]
    assert keys == ["lexuz", "govuz", "presidentuz", "eqaror", "ministries"]
    assert [p.key for p in all_policies() if p.can_be_enabled] == ["lexuz"]
    with pytest.raises(SourceNotEnabledError, match="EZO_OFFICIAL_SOURCES=lexuz"):
        get_connector("lexuz", enabled=[])
    assert get_connector("lexuz", enabled=["lexuz"]).policy.name == "LEX.UZ"
    for key in ("govuz", "presidentuz", "eqaror", "ministries"):
        with pytest.raises(UnsupportedSourceError, match="not been verified"):
            get_connector(key, enabled=[key])
    with pytest.raises(UnsupportedSourceError, match="Unknown"):
        get_connector("example", enabled=["example"])
    review = POLICY.review
    assert "Checked 2026-11-19" in review.robots_txt and "owner reviewed" in review.terms_of_use


# --- LEX.UZ live markup (checked 2026-11-19) ------------------------------------------------

_LX = (
    '<div class="{kind} lx_elem" onmousemove="lx_mo(event,{n})"><div class="lx_elem2">'
    '<div class="lx_elem3"><span onclick="lx_sf({n})"><img src="/img/cmt.svg" />Ҳужжатга '
    'таклиф юбориш</span></div></div><div name="{n}" id="{n}">{text}</div></div>'
)


def _lx_page(title: str, parts: list[tuple[str, str]]) -> bytes:
    body = "".join(_LX.format(kind=k, n=1000 + i, text=t) for i, (k, t) in enumerate(parts))
    note = (
        '<div class="COMMENT lx_no_select"><div name="edi1" id="edi1">'
        "Олдинги таҳрирга қаранг.</div></div>"
    )
    return f"<html><head><title>{title}</title></head><body>{body}{note}</body></html>".encode()


def test_lexuz_page_text_comes_from_its_elements_with_headings_and_without_notes() -> None:
    from ezo_api.knowledge.fetch import FetchedPage
    from ezo_api.official.base import DocumentRef
    from ezo_api.official.lexuz import LexUzConnector

    data = _lx_page(
        "&nbsp; 28.10.2022.&nbsp;Ўзбекистон Республикасининг Меҳнат кодекси",
        [
            ("TEXT_HEADER_DEFAULT", "УМУМИЙ ҚИСМ"),
            ("CLAUSE_DEFAULT", "1-модда. Ушбу Кодекс билан тартибга солинадиган муносабатлар"),
            ("ACT_TEXT", "Ушбу Кодекс ходимлар, иш берувчилар ва давлат манфаатларининг "
                         "мувозанатини таъминлаш асосида меҳнат муносабатларини тартибга солади."),
            ("BY_DEFAULT", ""),
        ],
    )  # fmt: skip
    page = FetchedPage("u", "https://lex.uz/docs/6257288", "text/html", data, 0.0)
    parsed = LexUzConnector().parse(page, DocumentRef("6257288", "uz"))
    assert parsed.title == "Ўзбекистон Республикасининг Меҳнат кодекси"
    assert str(parsed.adopted_on) == "2022-10-28"
    assert "## УМУМИЙ ҚИСМ" in parsed.text and "### 1-модда." in parsed.text
    assert "Олдинги таҳрирга" not in parsed.text  # editorial notes are not law text
    assert parsed.status_source == "unverified"  # the page itself states no status


def test_lexuz_search_list_and_url() -> None:
    from ezo_api.official.lexuz import parse_search, search_url

    html = (
        '<tr class="dd-table__main-item"><td><i class="fa status_code_y"></i>'
        '<a class="lx_link " href="/docs/6257288" target="_blank">Меҳнат кодекси</a>'
        '<span class="badge badge-pill badge-nine">Кодекс</span></td></tr>'
        '<tr class="dd-table__main-item"><td><i class="fa status_code_r"></i>'
        '<a class="lx_link " href="/docs/142859" target="_blank">Эски кодекс</a></td></tr>'
        '<tr class="dd-table__main-item"><td><i class="fa status_code_y"></i>'
        '<a class="lx_link " href="/docs/-8586150" target="_blank">Идоравий</a></td></tr>'
    )
    hits = parse_search(html)
    assert [(h.source_doc_id, h.status) for h in hits] == [
        ("6257288", "in_force"),
        ("142859", "repealed"),
    ]
    assert hits[0].details == "Кодекс"
    url = search_url("Mehnat kodeksi", exact=True)
    assert url.startswith("https://lex.uz/search/nat?searchtitle=") and "lang=3" in url
    assert "exact2=1" in url and "%D0%9C%D0%B5%D2%B3%D0%BD%D0%B0%D1%82" in url  # Меҳнат


@pytest.mark.parametrize(
    ("raw", "number", "adopted", "title"),
    [
        ("913-XII-сон 02.09.1993. О государственной власти на местах", "913-XII", "1993-09-02",
         "О государственной власти на местах"),
        ("  30.04.2023. Ўзбекистон Республикаси Конституцияси", None, "2023-04-30",
         "Ўзбекистон Республикаси Конституцияси"),
    ],
)  # fmt: skip
def test_lexuz_title_forms(raw: str, number: str | None, adopted: str, title: str) -> None:
    from ezo_api.official.legal_text import parse_title

    info = parse_title(raw)
    assert (info.number, str(info.adopted_on), info.title) == (number, adopted, title)


def test_hokimiyat_collection_is_well_formed() -> None:
    from ezo_api.official.collections import COLLECTIONS
    from ezo_api.official.lexuz import LexUzConnector

    items = COLLECTIONS["hokimiyat"].items
    ids = [i.source_doc_id for i in items]
    assert len(ids) == len(set(ids)) >= 10
    for doc_id in ids:
        assert LexUzConnector().validate_id(doc_id) == doc_id
