"""Academic helpers without a model or network: citation styles, OpenAlex parsing, plan
checks and field verification of extracted references."""

from __future__ import annotations

import json

import httpx
import pytest

from ezo_api.academic.citations import (
    Reference,
    clean_doi,
    format_list,
    in_text,
    style_from,
)
from ezo_api.academic.plan import Plan, check_plan, remove_bad_citations
from ezo_api.academic.requests import citation_request, wants_research_plan
from ezo_api.academic.scholar import OpenAlexClient, ScholarError, parse_work
from ezo_api.agents.academic_office import _Extracted, _verified
from ezo_api.knowledge.fetch import SafeFetcher

ARTICLE = Reference(
    title="Digital public services in Uzbekistan",
    authors=["Karimov, Akmal", "Dilnoza Yusupova"],
    year=2023,
    container="Journal of Public Administration",
    volume="12",
    issue="3",
    pages="45-67",
    doi="https://doi.org/10.1234/jpa.2023.45",
)
BOOK = Reference(
    title="Mahalliy boshqaruv asoslari",
    authors=["Rahimov, Bobur"],
    year=2019,
    kind="book",
    publisher="O'zbekiston",
    place="Toshkent",
)
WEB = Reference(
    title="Open data portal",
    kind="web",
    container="data.gov.uz",
    url="https://data.gov.uz",
    accessed="2026-10-18",
)


def test_styles() -> None:
    refs = [ARTICLE, BOOK, WEB]
    assert format_list(refs, "apa") == [
        "Karimov, A., & Yusupova, D. (2023). Digital public services in Uzbekistan. "
        "*Journal of Public Administration*, *12*(3), 45–67. https://doi.org/10.1234/jpa.2023.45",
        "*Open data portal.* (n.d.). data.gov.uz. https://data.gov.uz",
        "Rahimov, B. (2019). *Mahalliy boshqaruv asoslari.* O'zbekiston.",
    ]
    assert format_list([ARTICLE], "mla") == [
        "Karimov, Akmal, and Dilnoza Yusupova. “Digital public services in Uzbekistan.” "
        "*Journal of Public Administration*, vol. 12, no. 3, 2023, pp. 45–67. "
        "doi.org/10.1234/jpa.2023.45."
    ]
    assert format_list([ARTICLE], "chicago")[0].startswith(
        "Karimov, Akmal, and Dilnoza Yusupova. 2023. “Digital public services in Uzbekistan.” "
        "*Journal of Public Administration* 12 (3): 45–67."
    )
    assert format_list([WEB], "harvard") == [
        "Open data portal (n.d.) *data.gov.uz*. Available at: https://data.gov.uz "
        "(Accessed: 2026-10-18)."
    ]
    assert format_list([ARTICLE, BOOK], "ieee") == [
        "[1] A. Karimov and D. Yusupova, “Digital public services in Uzbekistan,” "
        "*Journal of Public Administration*, vol. 12, no. 3, pp. 45–67, 2023, "
        "doi: 10.1234/jpa.2023.45.",
        "[2] B. Rahimov, *Mahalliy boshqaruv asoslari*. Toshkent, O'zbekiston, 2019.",
    ]
    assert format_list([ARTICLE, WEB], "gost") == [
        "1. Karimov A. Digital public services in Uzbekistan / A. Karimov, D. Yusupova "
        "// Journal of Public Administration. — 2023. — Vol. 12, № 3. — P. 45–67. "
        "— DOI: 10.1234/jpa.2023.45.",
        "2. Open data portal [Electronic resource] // data.gov.uz. — s.a. — "
        "URL: https://data.gov.uz (accessed: 2026-10-18).",
    ]
    assert in_text(ARTICLE, "apa", 1) == "(Karimov & Yusupova, 2023)"
    assert in_text(ARTICLE, "chicago", 1) == "(Karimov and Yusupova 2023)"
    assert in_text(BOOK, "mla", 2) == "(Rahimov)" and in_text(BOOK, "ieee", 2) == "[2]"
    many = Reference(title="T", authors=["A B", "C D", "E F"], year=2020)
    assert in_text(many, "harvard", 1) == "(B et al., 2020)"
    assert WEB.missing() == ["authors", "year"] and ARTICLE.missing() == []
    surname_first = Reference(title="Raqamli hukumat", authors=["Karimov A.B."], year=2020)
    assert in_text(surname_first, "apa", 1) == "(Karimov, 2020)"
    assert clean_doi("doi: 10.1000/xyz") == "10.1000/xyz" and clean_doi("not a doi") == ""
    assert style_from("APA formatida") == "apa" and style_from("по ГОСТ") == "gost"


def test_requests() -> None:
    assert wants_research_plan(
        "Shu mavzu bo'yicha ilmiy manbalarni top, tadqiqot rejasini tuz va himoyaga tayyorlan"
    )
    assert wants_research_plan("Составь план исследования по экологии Арала")
    assert not wants_research_plan("Bugun havo qanday?")
    assert citation_request("Shu adabiyotlarni APA formatiga o'tkaz: …") == "apa"
    assert citation_request("Оформи список литературы по ГОСТ") == "gost"
    assert citation_request("APA nima?") is None


OPENALEX_ITEM = {
    "id": "https://openalex.org/W123",
    "doi": "https://doi.org/10.5555/egov.2021.7",
    "display_name": "E-government adoption in Central Asia",
    "publication_year": 2021,
    "type": "article",
    "authorships": [
        {"author": {"display_name": "Aziza Nazarova"}},
        {"author": {"display_name": "John Smith"}},
    ],
    "primary_location": {
        "source": {"display_name": "Government Information Quarterly"},
        "landing_page_url": "https://example.org/egov",
    },
    "biblio": {"volume": "38", "issue": "2", "first_page": "101", "last_page": "115"},
    "cited_by_count": 42,
    "open_access": {"oa_url": "https://example.org/egov.pdf"},
    "abstract_inverted_index": {"This": [0], "study": [1], "reviews": [2], "adoption": [3]},
    "language": "en",
}


def test_openalex_parsing_and_search() -> None:
    work = parse_work(OPENALEX_ITEM)
    assert work is not None
    ref = work.reference
    assert (ref.title, ref.year, ref.authors) == (
        "E-government adoption in Central Asia",
        2021,
        ["Aziza Nazarova", "John Smith"],
    )
    assert (ref.container, ref.volume, ref.issue, ref.pages, ref.doi) == (
        "Government Information Quarterly",
        "38",
        "2",
        "101-115",
        "10.5555/egov.2021.7",
    )
    assert work.abstract == "This study reviews adoption" and work.cited_by == 42
    assert parse_work({"display_name": ""}) is None


async def test_openalex_client_uses_the_safe_fetcher() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"results": [OPENALEX_ITEM]}, headers={"content-type": "application/json"}
        )

    async def resolve(host: str, port: int) -> list[str]:
        return ["93.184.216.34"]

    client = OpenAlexClient(
        SafeFetcher(transport=httpx.MockTransport(handler), resolver=resolve), mailto="a@b.uz"
    )
    works = await client.search("e-government Central Asia", 5, from_year=2018)
    assert [w.reference.title for w in works] == ["E-government adoption in Central Asia"]
    url = str(seen[0].url)
    assert url.startswith("https://api.openalex.org/works?search=e-government+Central+Asia")
    assert "per-page=5" in url and "from_publication_date%3A2018-01-01" in url
    assert "mailto=a%40b.uz" in url and seen[0].headers["accept"] == "application/json"

    def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html></html>", headers={"content-type": "text/html"})

    bad = OpenAlexClient(SafeFetcher(transport=httpx.MockTransport(html), resolver=resolve))
    with pytest.raises(ScholarError):
        await bad.search("x")


def test_plan_checks() -> None:
    plan = Plan.model_validate(
        {
            "research_questions": ["How is e-government adopted? [1]"],
            "literature_review": [
                {"theme": "Adoption", "text": "Adoption grows [1, 3]. Results show trust matters."},
            ],
            "hypotheses": ["Trust increases adoption."],
        }
    )
    report = check_plan(plan, works=2)
    assert report.cited == [1] and report.bad_citations == ["[3]"]
    assert report.unsupported_results == ["Results show trust matters."]
    assert remove_bad_citations("Adoption grows [1, 3]. See [9].", 2) == "Adoption grows [1]. See ."
    assert json.dumps(report.summary())


def test_extracted_fields_must_be_in_the_text() -> None:
    text = "Karimov A. Raqamli hukumat. Toshkent: Fan, 2020."
    ref, dropped = _verified(
        _Extracted(
            kind="book",
            authors=["Karimov A.", "Invented Person"],
            year=2021,
            title="Raqamli hukumat",
            publisher="Fan",
            place="Toshkent",
            doi="10.9999/made.up",
        ),
        text,
    )
    assert ref is not None
    assert ref.authors == ["Karimov A."] and ref.year is None and ref.doi == ""
    assert (ref.publisher, ref.place) == ("Fan", "Toshkent")
    assert dropped == ["author “Invented Person”", "doi", "year"]
    missing, why = _verified(_Extracted(title="Not in the text"), text)
    assert missing is None and why == ["title"]
