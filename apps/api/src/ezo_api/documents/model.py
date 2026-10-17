"""A small, format-neutral document model.

Models write Markdown (the most reliable format for them); `markdown_io` turns it
into this model, and every writer (DOCX, PDF, Markdown, TXT) renders from it, so
all formats show the same structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    link: str | None = None


@dataclass(frozen=True, slots=True)
class Heading:
    level: int  # 1..4
    runs: tuple[Run, ...]
    kind: Literal["heading"] = "heading"


@dataclass(frozen=True, slots=True)
class Paragraph:
    runs: tuple[Run, ...]
    kind: Literal["paragraph"] = "paragraph"


@dataclass(frozen=True, slots=True)
class ListBlock:
    items: tuple[tuple[Run, ...], ...]
    ordered: bool = False
    kind: Literal["list"] = "list"


@dataclass(frozen=True, slots=True)
class Table:
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    kind: Literal["table"] = "table"


@dataclass(frozen=True, slots=True)
class Quote:
    runs: tuple[Run, ...]
    kind: Literal["quote"] = "quote"


@dataclass(frozen=True, slots=True)
class CodeBlock:
    text: str
    kind: Literal["code"] = "code"


@dataclass(frozen=True, slots=True)
class Rule:
    kind: Literal["rule"] = "rule"


Block = Heading | Paragraph | ListBlock | Table | Quote | CodeBlock | Rule


@dataclass(slots=True)
class DocumentSpec:
    title: str
    blocks: list[Block] = field(default_factory=list)
    subtitle: str = ""
    language: str = "uz"
    author: str = "EZO"


def plain(runs: tuple[Run, ...]) -> str:
    return "".join(run.text for run in runs)


def word_count(spec: DocumentSpec) -> int:
    words = 0
    for block in spec.blocks:
        if isinstance(block, Heading | Paragraph | Quote):
            words += len(plain(block.runs).split())
        elif isinstance(block, ListBlock):
            words += sum(len(plain(item).split()) for item in block.items)
        elif isinstance(block, Table):
            words += sum(len(cell.split()) for row in (block.header, *block.rows) for cell in row)
        elif isinstance(block, CodeBlock):
            words += len(block.text.split())
    return words
