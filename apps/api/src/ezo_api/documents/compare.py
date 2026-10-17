"""Compare two texts paragraph by paragraph (difflib): what was added, removed, changed."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field


@dataclass(slots=True)
class Comparison:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[tuple[str, str]] = field(default_factory=list)
    similarity: float = 1.0

    @property
    def identical(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def summary(self) -> str:
        return (
            f"{len(self.changed)} changed, {len(self.added)} added, {len(self.removed)} removed "
            f"paragraphs; similarity {self.similarity:.0%}"
        )

    def to_markdown(self, limit: int = 40) -> str:
        parts = [f"**{self.summary()}**"]
        for old, new in self.changed[:limit]:
            parts.append(f"- ~~{old[:400]}~~\n  → {new[:400]}")
        for text in self.added[:limit]:
            parts.append(f"- ➕ {text[:400]}")
        for text in self.removed[:limit]:
            parts.append(f"- ➖ ~~{text[:400]}~~")
        return "\n".join(parts)


def paragraphs(text: str) -> list[str]:
    return [
        " ".join(p.split()) for p in re.split(r"\n\s*\n|\n(?=[-*•#]|\d+[.)])", text) if p.strip()
    ]


def compare_texts(original: str, edited: str) -> Comparison:
    old, new = paragraphs(original), paragraphs(edited)
    result = Comparison(
        similarity=difflib.SequenceMatcher(None, " ".join(old), " ".join(new)).ratio()
    )
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            pairs = min(i2 - i1, j2 - j1)
            result.changed.extend(zip(old[i1 : i1 + pairs], new[j1 : j1 + pairs], strict=True))
            result.removed.extend(old[i1 + pairs : i2])
            result.added.extend(new[j1 + pairs : j2])
        elif tag == "delete":
            result.removed.extend(old[i1:i2])
        elif tag == "insert":
            result.added.extend(new[j1:j2])
    return result
