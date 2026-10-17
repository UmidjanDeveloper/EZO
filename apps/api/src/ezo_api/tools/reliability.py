"""Source reliability scoring (transparent heuristics, 0..1).

Primary/official sources rank highest; social media and forums lowest. The
score guides ranking and is shown to the model; it is not a fact check.
"""

from __future__ import annotations

from urllib.parse import urlsplit

PRIMARY_DOMAINS = (
    "lex.uz",
    "president.uz",
    "gov.uz",
    "my.gov.uz",
    "regulation.gov.uz",
    "stat.uz",
    "cbu.uz",
    "un.org",
    "who.int",
    "worldbank.org",
    "imf.org",
    "oecd.org",
    "europa.eu",
    "ielts.org",
    "britishcouncil.org",
    "w3.org",
    "ietf.org",
    "python.org",
    "nodejs.org",
)
ACADEMIC_DOMAINS = (
    "arxiv.org",
    "nature.com",
    "science.org",
    "springer.com",
    "sciencedirect.com",
    "ncbi.nlm.nih.gov",
    "pubmed.ncbi.nlm.nih.gov",
    "acm.org",
    "ieee.org",
)
NEWS_DOMAINS = (
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "ft.com",
    "bloomberg.com",
    "nytimes.com",
    "theguardian.com",
    "economist.com",
    "kun.uz",
    "gazeta.uz",
    "daryo.uz",
    "uza.uz",
    "dunyo.info",
    "spot.uz",
    "podrobno.uz",
)
REFERENCE_DOMAINS = ("wikipedia.org", "britannica.com", "developer.mozilla.org", "docs.python.org")
LOW_DOMAINS = (
    "reddit.com",
    "quora.com",
    "medium.com",
    "facebook.com",
    "x.com",
    "twitter.com",
    "t.me",
    "instagram.com",
    "tiktok.com",
    "youtube.com",
    "pinterest.com",
    "blogspot.com",
    "wordpress.com",
)


def _matches(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def score_url(url: str) -> tuple[float, bool, str]:
    """Return (reliability, is_primary, tier)."""
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    if not host:
        return 0.3, False, "unknown"
    if (
        _matches(host, PRIMARY_DOMAINS)
        or host.endswith((".gov", ".gov.uz", ".mil"))
        or ".gov." in host
    ):
        return 0.95, True, "official"
    if (
        _matches(host, ACADEMIC_DOMAINS)
        or host.endswith(".edu")
        or ".ac." in host
        or host.endswith(".edu.uz")
    ):
        return 0.85, True, "academic"
    if _matches(host, NEWS_DOMAINS):
        return 0.7, False, "news"
    if _matches(host, REFERENCE_DOMAINS):
        return 0.65, False, "reference"
    if _matches(host, LOW_DOMAINS):
        return 0.35, False, "social"
    return 0.5, False, "general"
