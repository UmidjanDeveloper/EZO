"""All official sources EZO knows, in the order they are planned.

Only LEX.UZ has a connector (proof of concept). The others are listed with an
honest "unverified" access review: no endpoint is invented for them, and they
cannot be enabled until their access method, terms, robots.txt and limits have
been checked and a connector has been written.
"""

from __future__ import annotations

from datetime import date

from ezo_api.official.base import (
    AccessReview,
    OfficialSourceConnector,
    SourceNotEnabledError,
    SourcePolicy,
    UnsupportedSourceError,
)
from ezo_api.official.lexuz import LexUzConnector

_NOT_REVIEWED = "Not verified yet (host unreachable from EZO's build environment)."


def _planned(key: str, name: str, base_url: str, hosts: set[str], notes: str) -> SourcePolicy:
    return SourcePolicy(
        key=key,
        name=name,
        base_url=base_url,
        allowed_hosts=frozenset(hosts),
        access="unverified",
        languages=("uz", "ru"),
        review=AccessReview(
            reviewed_on=date(2026, 10, 18),
            official_api=_NOT_REVIEWED,
            robots_txt=_NOT_REVIEWED,
            terms_of_use=_NOT_REVIEWED,
            formats=_NOT_REVIEWED,
            rate_limits=_NOT_REVIEWED,
            legal_basis=_NOT_REVIEWED,
        ),
        notes=notes,
    )


PLANNED: dict[str, SourcePolicy] = {
    policy.key: policy
    for policy in (
        _planned(
            "govuz",
            "gov.uz",
            "https://gov.uz",
            {"gov.uz", "www.gov.uz"},
            "Government portal and ministry news. Connector after an access review.",
        ),
        _planned(
            "presidentuz",
            "president.uz",
            "https://president.uz",
            {"president.uz"},
            "Presidential decrees and news. Connector after an access review.",
        ),
        _planned(
            "eqaror",
            "E-qaror",
            "https://e-qaror.gov.uz",
            {"e-qaror.gov.uz"},
            "Decisions of local authorities. Connector after an access review.",
        ),
        _planned(
            "ministries",
            "Ministry and education sites",
            "",
            set(),
            "One adapter per site, each after its own access review.",
        ),
    )
}

CONNECTORS: dict[str, OfficialSourceConnector] = {"lexuz": LexUzConnector()}


def all_policies() -> list[SourcePolicy]:
    return [c.policy for c in CONNECTORS.values()] + list(PLANNED.values())


def get_connector(key: str, enabled: list[str]) -> OfficialSourceConnector:
    """The connector for `key`, only if it exists, is verified and is enabled in settings."""
    connector = CONNECTORS.get(key)
    if connector is None:
        if key in PLANNED:
            raise UnsupportedSourceError(
                f"{PLANNED[key].name} is not available yet: its access method has not been "
                "verified, so EZO has no connector for it."
            )
        raise UnsupportedSourceError(f"Unknown official source: {key}.")
    if key not in enabled:
        raise SourceNotEnabledError(
            f"{connector.policy.name} is not enabled. Review its access terms, then set "
            f"EZO_OFFICIAL_SOURCES={key} in .env."
        )
    return connector
