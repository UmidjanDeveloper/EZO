"""Markdown ⇄ DocumentSpec (the subset models write: headings, lists, tables, quotes,
code fences, rules, **bold**, *italic*, `code`, [links](url))."""

from __future__ import annotations

import re

from ezo_api.documents.model import (
    Block,
    CodeBlock,
    DocumentSpec,
    Heading,
    ListBlock,
    Paragraph,
    Quote,
    Rule,
    Run,
    Table,
    plain,
)

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^\s*[-*+•]\s+(.*)$")
_ORDERED = re.compile(r"^\s*\d{1,3}[.)]\s+(.*)$")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_INLINE = re.compile(
    r"(\*\*[^*]+\*\*|__[^_]+__|\*[^*\s][^*]*\*|_[^_\s][^_]*_|`[^`]+`|\[[^\]]+\]\([^)\s]+\))"
)


def parse_inline(text: str) -> tuple[Run, ...]:
    runs: list[Run] = []
    position = 0
    for match in _INLINE.finditer(text):
        if match.start() > position:
            runs.append(Run(text[position : match.start()]))
        token = match.group(0)
        if token.startswith(("**", "__")):
            runs.append(Run(token[2:-2], bold=True))
        elif token.startswith("`"):
            runs.append(Run(token[1:-1], code=True))
        elif token.startswith("["):
            label, url = token[1:].split("](", 1)
            runs.append(
                Run(label, link=url[:-1] if url[:-1].startswith(("http://", "https://")) else None)
            )
        else:
            runs.append(Run(token[1:-1], italic=True))
        position = match.end()
    if position < len(text):
        runs.append(Run(text[position:]))
    return tuple(run for run in runs if run.text)


def _cells(line: str) -> tuple[str, ...]:
    line = line.strip().strip("|")
    return tuple(cell.strip().replace("**", "") for cell in line.split("|"))


def parse_markdown(markdown: str, title: str | None = None) -> DocumentSpec:
    """Parse Markdown. The first level-1 heading becomes the title unless one is given."""
    lines = markdown.replace("\r\n", "\n").split("\n")
    blocks: list[Block] = []
    paragraph: list[str] = []
    i = 0

    def flush() -> None:
        if paragraph:
            text = " ".join(part.strip() for part in paragraph).strip()
            if text:
                blocks.append(Paragraph(parse_inline(text)))
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            flush()
            i += 1
            continue
        if stripped.startswith("```"):
            flush()
            code: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            blocks.append(CodeBlock("\n".join(code)))
            i += 1
            continue
        heading = _HEADING.match(stripped)
        if heading:
            flush()
            blocks.append(Heading(min(len(heading.group(1)), 4), parse_inline(heading.group(2))))
            i += 1
            continue
        if _RULE.match(stripped):
            flush()
            blocks.append(Rule())
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]):
            flush()
            header = _cells(stripped)
            rows: list[tuple[str, ...]] = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = _cells(lines[i])
                rows.append(tuple((cells + ("",) * len(header))[: len(header)]))
                i += 1
            blocks.append(Table(header, tuple(rows)))
            continue
        if stripped.startswith(">"):
            flush()
            quoted: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quoted.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append(Quote(parse_inline(" ".join(quoted))))
            continue
        bullet, ordered = _BULLET.match(line), _ORDERED.match(line)
        if bullet or ordered:
            flush()
            is_ordered = bool(ordered) and not bullet
            items: list[tuple[Run, ...]] = []
            while i < len(lines):
                match = (_ORDERED if is_ordered else _BULLET).match(lines[i])
                if match:
                    items.append(parse_inline(match.group(1).strip()))
                elif lines[i].startswith(("  ", "\t")) and lines[i].strip() and items:
                    items[-1] = (
                        items[-1] + (Run(" "),) + parse_inline(lines[i].strip())
                    )  # continuation
                else:
                    break
                i += 1
            blocks.append(ListBlock(tuple(items), ordered=is_ordered))
            continue
        paragraph.append(stripped)
        i += 1
    flush()

    doc_title = title
    if doc_title is None:
        first = next((b for b in blocks if isinstance(b, Heading) and b.level == 1), None)
        if first is not None:
            doc_title = plain(first.runs)
            blocks.remove(first)
    # The title is not a heading: the shallowest remaining heading becomes level 1.
    levels = [b.level for b in blocks if isinstance(b, Heading)]
    if levels and min(levels) > 1:
        shift = min(levels) - 1
        blocks = [Heading(b.level - shift, b.runs) if isinstance(b, Heading) else b for b in blocks]
    return DocumentSpec(title=(doc_title or "Hujjat").strip(), blocks=blocks)


def _runs_md(runs: tuple[Run, ...]) -> str:
    out = []
    for run in runs:
        text = run.text
        if run.code:
            text = f"`{text}`"
        if run.bold:
            text = f"**{text}**"
        if run.italic:
            text = f"*{text}*"
        if run.link:
            text = f"[{text}]({run.link})"
        out.append(text)
    return "".join(out)


def to_markdown(spec: DocumentSpec) -> str:
    parts = [f"# {spec.title}"]
    if spec.subtitle:
        parts.append(f"*{spec.subtitle}*")
    for block in spec.blocks:
        if isinstance(block, Heading):
            parts.append(f"{'#' * min(block.level + 1, 6)} {_runs_md(block.runs)}")
        elif isinstance(block, Paragraph):
            parts.append(_runs_md(block.runs))
        elif isinstance(block, ListBlock):
            parts.append(
                "\n".join(
                    f"{index}. {_runs_md(item)}" if block.ordered else f"- {_runs_md(item)}"
                    for index, item in enumerate(block.items, start=1)
                )
            )
        elif isinstance(block, Table):
            rows = [block.header, tuple("---" for _ in block.header), *block.rows]
            parts.append(
                "\n".join(
                    "| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |"
                    for row in rows
                )
            )
        elif isinstance(block, Quote):
            parts.append(f"> {_runs_md(block.runs)}")
        elif isinstance(block, CodeBlock):
            parts.append(f"```\n{block.text}\n```")
        elif isinstance(block, Rule):
            parts.append("---")
    return "\n\n".join(parts) + "\n"


def to_text(spec: DocumentSpec) -> str:
    """Plain text with simple, readable structure."""
    parts = [spec.title.upper(), "=" * min(len(spec.title), 60)]
    if spec.subtitle:
        parts.append(spec.subtitle)
    for block in spec.blocks:
        if isinstance(block, Heading):
            text = plain(block.runs)
            parts.append(text.upper() if block.level == 1 else text)
        elif isinstance(block, Paragraph | Quote):
            parts.append(plain(block.runs))
        elif isinstance(block, ListBlock):
            parts.append(
                "\n".join(
                    f"{index}. {plain(item)}" if block.ordered else f"• {plain(item)}"
                    for index, item in enumerate(block.items, start=1)
                )
            )
        elif isinstance(block, Table):
            parts.append("\n".join(" | ".join(row) for row in (block.header, *block.rows)))
        elif isinstance(block, CodeBlock):
            parts.append(block.text)
        elif isinstance(block, Rule):
            parts.append("-" * 40)
    return "\n\n".join(parts) + "\n"
