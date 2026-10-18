"""Academic helpers: reference lists in a citation style (deterministic) and scholarly
literature search (OpenAlex)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ezo_api.academic.citations import STYLE_NAMES, STYLES, Reference, Style, format_list
from ezo_api.academic.scholar import ScholarError
from ezo_api.api.deps import CurrentUser, ServicesDep, rate_limit

router = APIRouter(prefix="/api/academic", tags=["academic"])


class ReferenceIn(BaseModel):
    title: str = Field(min_length=1, max_length=1_000)
    authors: list[str] = Field(default_factory=list, max_length=50)
    year: int | None = Field(default=None, ge=1000, le=2200)
    kind: Literal["article", "book", "chapter", "web", "thesis", "report"] = "article"
    container: str = Field(default="", max_length=500)
    volume: str = Field(default="", max_length=50)
    issue: str = Field(default="", max_length=50)
    pages: str = Field(default="", max_length=50)
    publisher: str = Field(default="", max_length=300)
    place: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=2_000)
    doi: str = Field(default="", max_length=300)
    accessed: str = Field(default="", max_length=20)


class CiteIn(BaseModel):
    style: Style
    references: list[ReferenceIn] = Field(min_length=1, max_length=500)


@router.get("/styles", dependencies=[Depends(rate_limit("default"))])
async def styles(_: CurrentUser) -> list[dict[str, str]]:
    return [{"key": key, "name": STYLE_NAMES[key]} for key in STYLES]


@router.post("/cite", dependencies=[Depends(rate_limit("default"))])
async def cite(body: CiteIn, _: CurrentUser) -> dict[str, Any]:
    """Format references by fixed style rules (no model); missing fields are listed."""
    references = [Reference(**r.model_dump()) for r in body.references]
    return {
        "style": body.style,
        "entries": format_list(references, body.style),
        "missing": [{"title": r.title, "fields": r.missing()} for r in references if r.missing()],
    }


@router.get("/search", dependencies=[Depends(rate_limit("chat"))])
async def search(
    services: ServicesDep,
    _: CurrentUser,
    q: str = Query(min_length=2, max_length=300),
    limit: int = Query(default=10, ge=1, le=25),
    from_year: int | None = Query(default=None, ge=1900, le=2100),
) -> dict[str, Any]:
    if services.scholar is None:
        raise HTTPException(
            503, detail={"code": "scholar_off", "message": "Scholarly search is turned off."}
        )
    try:
        works = await services.scholar.search(q, limit, from_year)
    except ScholarError as exc:
        raise HTTPException(502, detail={"code": "scholar_failed", "message": exc.message}) from exc
    return {
        "provider": services.scholar.name,
        "works": [
            {
                "title": w.reference.title,
                "authors": w.reference.authors,
                "year": w.reference.year,
                "container": w.reference.container,
                "doi": w.reference.doi,
                "url": w.reference.url,
                "cited_by": w.cited_by,
                "open_access_url": w.open_access_url,
                "apa": format_list([w.reference], "apa")[0],
            }
            for w in works
        ],
    }
