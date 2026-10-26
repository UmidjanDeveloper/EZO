"""One place that decides what memory consent allows (audit finding F18).

- ``memory_consent``: the user agrees that EZO may keep memories at all.
- ``auto_memory``: EZO may capture memories from conversations (needs consent).
- ``memory_recall``: saved memories, including ones saved explicitly by hand, may be
  brought into replies. ``None`` follows ``memory_consent``.

Revoking consent stops automatic capture **and** recall into replies. Saved memories
stay visible, editable, exportable and deletable on the Memory page; they are not
used in conversations unless the user explicitly turns recall back on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    consent: bool
    capture: bool
    recall: bool


def memory_policy(preferences: Mapping[str, Any] | None) -> MemoryPolicy:
    prefs = preferences or {}
    consent = bool(prefs.get("memory_consent", False))
    explicit = prefs.get("memory_recall")
    recall = consent if explicit is None else bool(explicit)
    return MemoryPolicy(
        consent=consent, capture=consent and bool(prefs.get("auto_memory")), recall=recall
    )


def apply_consent_change(preferences: dict[str, Any], fields: Mapping[str, Any]) -> dict[str, Any]:
    """Merge a preferences change, keeping capture and recall consistent with consent.

    Revoking consent turns automatic capture off and resets recall to "follow consent"
    (off), unless the same request explicitly asks to keep recalling saved memories.
    """
    merged = {**preferences, **fields}
    if not merged.get("memory_consent"):
        merged["auto_memory"] = False
        if "memory_recall" not in fields and preferences.get("memory_consent"):
            merged["memory_recall"] = None
    return merged
