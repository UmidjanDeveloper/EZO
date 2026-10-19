"""Checks on what EZO reads from outside: prompt-injection attempts and licences.

External text is always data. Nothing here changes it or acts on it: suspicious
passages are *flagged* (recorded on the source, audit-logged, shown to the owner) so a
person can see that a page tried to give EZO instructions. Retrieval keeps wrapping the
text in <source> tags with the rule that sources are not instructions.

The licence assessment is a first reading for a commercial, closed-source service, not
legal advice: anything other than a well-known permissive licence is marked for review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_INJECTION = [
    (
        "override",
        r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|earlier|all|your)\b.{0,30}"
        r"\b(instructions?|rules|prompts?|directions)\b",
    ),
    ("role", r"\b(you are now|act as|pretend to be)\b.{0,60}\b(assistant|ai|model|system|admin)"),
    ("system_prompt", r"\b(system prompt|developer message|hidden instructions?)\b"),
    (
        "secrets",
        r"\b(reveal|print|send|exfiltrate|leak|show)\b.{0,40}\b(api[ _-]?keys?|secrets?|"
        r"passwords?|tokens?|credentials|\.env)\b",
    ),
    (
        "execution",
        r"\b(run|execute)\b.{0,30}\b(this|the following)\b.{0,20}\b(command|script|code)\b"
        r"|curl\s+[^|\n]{0,200}\|\s*(ba)?sh\b",
    ),
    ("uz_override", r"\b(oldingi|avvalgi|barcha)\b.{0,30}\b(ko'rsatmalar|buyruqlar)\w*\b.{0,30}"
     r"\b(e'tibor berma|unut|bekor qil)"),
    ("ru_override", r"\b(игнорируй|забудь|не обращай внимания)\b.{0,40}\b(инструкци|правил)"),
]  # fmt: skip
_COMPILED = [(name, re.compile(pattern, re.I | re.S)) for name, pattern in _INJECTION]
MAX_FLAGS = 20


@dataclass(frozen=True, slots=True)
class Flag:
    kind: str
    location: str
    excerpt: str

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "location": self.location, "excerpt": self.excerpt}


def scan_text(text: str, location: str, limit: int = 5) -> list[Flag]:
    """Passages that look like instructions aimed at an AI assistant."""
    flags: list[Flag] = []
    for kind, pattern in _COMPILED:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 40)
            excerpt = " ".join(text[start : match.end() + 40].split())[:240]
            flags.append(Flag(kind, location, excerpt))
            if len(flags) >= limit:
                return flags
    return flags


# SPDX identifiers (or common names) that are usually fine in a closed commercial service
# when their notices are kept.
PERMISSIVE = {
    "mit", "mit-0", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "0bsd", "isc", "zlib",
    "unlicense", "cc0-1.0", "psf-2.0", "python-2.0", "bsl-1.0", "cc-by-4.0",
}  # fmt: skip
# Copyleft or restricted: allowed to read and learn from, but code or copies need review.
REVIEW = {
    "gpl-2.0", "gpl-3.0", "lgpl-2.1", "lgpl-3.0", "agpl-3.0", "mpl-2.0", "epl-2.0",
    "sspl-1.0", "busl-1.1", "cc-by-sa-4.0", "cc-by-nc-4.0", "cc-by-nd-4.0", "eupl-1.2",
    "osl-3.0", "cddl-1.0",
}  # fmt: skip
_ALIASES = {
    "mit license": "mit",
    "apache 2.0": "apache-2.0",
    "apache license 2.0": "apache-2.0",
    "apache software license": "apache-2.0",
    "apache-2": "apache-2.0",
    "bsd license": "bsd-3-clause",
    "bsd": "bsd-3-clause",
    "new bsd license": "bsd-3-clause",
    "isc license": "isc",
    "python software foundation license": "psf-2.0",
    "gnu general public license v3 (gplv3)": "gpl-3.0",
    "gnu general public license v2 (gplv2)": "gpl-2.0",
    "gnu lesser general public license v3 (lgplv3)": "lgpl-3.0",
    "gnu affero general public license v3": "agpl-3.0",
    "mozilla public license 2.0 (mpl 2.0)": "mpl-2.0",
    "gplv3": "gpl-3.0",
    "gplv2": "gpl-2.0",
    "lgpl": "lgpl-3.0",
    "agpl": "agpl-3.0",
}


def normalize_license(value: str | None) -> str | None:
    if not value:
        return None
    text = " ".join(str(value).split()).strip()
    if not text or text.lower() in ("unknown", "none", "noassertion", "other", "unlicensed"):
        return None
    lowered = text.lower()
    if lowered.startswith("license :: osi approved :: "):
        lowered = lowered.removeprefix("license :: osi approved :: ")
    lowered = _ALIASES.get(lowered, lowered)
    return lowered if lowered in PERMISSIVE | REVIEW else text[:200]


def assess_license(value: str | None) -> dict[str, str | bool | None]:
    """{"license", "category", "needs_review", "note"} for the owner (not legal advice)."""
    spdx = normalize_license(value)
    if spdx is None:
        return {
            "license": None,
            "category": "unknown",
            "needs_review": True,
            "note": "No licence found: you may read the documentation, but do not copy or "
            "ship its code before the owner's terms are clear.",
        }
    key = spdx.lower()
    if key in PERMISSIVE:
        return {
            "license": spdx,
            "category": "permissive",
            "needs_review": False,
            "note": "Permissive licence: keep its copyright and licence notice when code or "
            "substantial text is reused.",
        }
    if key in REVIEW:
        return {
            "license": spdx,
            "category": "copyleft_or_restricted",
            "needs_review": True,
            "note": "Copyleft or restricted licence: using its code in a closed commercial "
            "service can create obligations. Legal review needed before integrating code.",
        }
    return {
        "license": spdx,
        "category": "other",
        "needs_review": True,
        "note": "Unrecognised licence text: review it before reusing code.",
    }
