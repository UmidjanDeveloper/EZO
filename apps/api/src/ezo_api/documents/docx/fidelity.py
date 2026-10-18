"""Edit an existing Word document in place, keeping its formatting.

Instead of regenerating the document, EZO changes the text of existing paragraphs and
leaves everything else as it was: styles, fonts, numbering, tables, images, headers and
footers, section settings, comments and bookmarks.

Inside a paragraph, text lives in *runs* that carry the formatting (bold, colour,
font...). A paragraph's runs are grouped into *segments* of identical formatting. When
a paragraph has several segments, the text given to the model marks the non-dominant
ones as ``⟦1⟧bold words⟦/1⟧`` so the new text can keep them. If the markers come back
broken, small edits are mapped onto the runs character by character (difflib); only
if that is impossible does the paragraph fall back to its dominant formatting, with a
warning.

Paragraphs that contain fields (page numbers, tables of contents), existing tracked
changes, content controls or equations are not changed; they are reported.

Optionally the edit is recorded as real Word tracked changes (``w:del`` / ``w:ins``,
author "EZO"): word by word for paragraphs with uniform formatting, otherwise the old
paragraph text is marked deleted and the new text inserted.
"""

from __future__ import annotations

import copy
import hashlib
import io
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn
from lxml import etree

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_DOCX_BYTES = 50 * 1024 * 1024
TAB, BREAK = "⟨TAB⟩", "⟨BR⟩"
_MARK = re.compile(r"⟦(\d{1,3})⟧(.*?)⟦/\1⟧", re.DOTALL)
_ANY_MARK = re.compile(r"⟦/?\d{1,3}⟧")
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

_TEXT_CHILDREN = {qn("w:t"), qn("w:tab"), qn("w:br"), qn("w:cr"), qn("w:noBreakHyphen")}
_IGNORED_RUN_CHILDREN = {qn("w:rPr"), qn("w:lastRenderedPageBreak"), qn("w:softHyphen")}
_KEPT_IN_PLACE = {
    qn("w:pPr"),
    qn("w:bookmarkStart"),
    qn("w:bookmarkEnd"),
    qn("w:proofErr"),
    qn("w:commentRangeStart"),
    qn("w:commentRangeEnd"),
    qn("w:permStart"),
    qn("w:permEnd"),
}
_PROTECTED = {
    qn("w:ins"): "tracked changes",
    qn("w:del"): "tracked changes",
    qn("w:moveFrom"): "tracked changes",
    qn("w:moveTo"): "tracked changes",
    qn("w:sdt"): "a content control",
    qn("w:customXml"): "custom XML",
    qn("w:smartTag"): "a smart tag",
    "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath": "an equation",
    "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMathPara": "an equation",
}
_SIGNATURE_IGNORED = {qn("w:lang"), qn("w:noProof"), qn("w:rtl")}


class DocxEditError(Exception):
    def __init__(self, message: str, code: str = "bad_docx") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


# --------------------------------------------------------------------------- reading


@dataclass(slots=True)
class Segment:
    runs: list[Any]
    text: str
    signature: str
    hyperlink: Any | None = None


@dataclass(slots=True)
class Unit:
    """One paragraph of the document (body, table cell, text box, header or footer)."""

    index: int
    part: str
    element: Any
    segments: list[Segment]
    protected: str | None = None
    has_anchor_between_text: bool = False

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.segments)

    @property
    def dominant(self) -> Segment:
        plain = [s for s in self.segments if s.hyperlink is None] or self.segments
        weight: Counter[str] = Counter()
        for segment in plain:
            weight[segment.signature] += len(segment.text) or 1
        best = weight.most_common(1)[0][0]
        return next(s for s in plain if s.signature == best)

    def encode(self) -> tuple[str, dict[int, Segment]]:
        """Text for the model, with ⟦k⟧ markers around non-dominant formatting."""
        dominant = self.dominant
        marks: dict[int, Segment] = {}
        parts: list[str] = []
        for segment in self.segments:
            text = _escape(segment.text)
            if segment.signature == dominant.signature and segment.hyperlink is None:
                parts.append(text)
            elif text.strip():
                k = len(marks) + 1
                marks[k] = segment
                parts.append(f"⟦{k}⟧{text}⟦/{k}⟧")
            else:
                parts.append(text)
        return "".join(parts), marks


def _escape(text: str) -> str:
    return text.replace("\t", TAB).replace("\n", BREAK)


def _unescape(text: str) -> str:
    return text.replace(TAB, "\t").replace(BREAK, "\n")


def _run_text(run: Any) -> str | None:
    """Text of a pure text run, or None when the run holds something else (an image,
    a field code, a footnote reference...)."""
    parts: list[str] = []
    for child in run:
        tag = child.tag
        if tag in _IGNORED_RUN_CHILDREN:
            continue
        if tag == qn("w:t"):
            parts.append(child.text or "")
        elif tag == qn("w:tab"):
            parts.append("\t")
        elif tag == qn("w:br"):
            if child.get(qn("w:type")) not in (None, "textWrapping"):
                return None  # page or column break: keep the run as it is
            parts.append("\n")
        elif tag == qn("w:cr"):
            parts.append("\n")
        elif tag == qn("w:noBreakHyphen"):
            parts.append("‑")
        else:
            return None
    return "".join(parts)


def _signature(run: Any, hyperlink: Any | None) -> str:
    rpr = run.find(qn("w:rPr"))
    body = b""
    if rpr is not None:
        clean = copy.deepcopy(rpr)
        for child in list(clean):
            if child.tag in _SIGNATURE_IGNORED:
                clean.remove(child)
        body = etree.tostring(clean)
    link = f"link:{id(hyperlink)}" if hyperlink is not None else ""
    return link + hashlib.sha1(body, usedforsecurity=False).hexdigest()


def _unit(index: int, part: str, paragraph: Any) -> Unit:
    items: list[tuple[Any, Any | None, str]] = []  # (run, hyperlink, text)
    protected: str | None = None
    anchor_seen_after_text = False
    anchor_between = False

    def add_run(run: Any, hyperlink: Any | None) -> None:
        nonlocal anchor_seen_after_text, anchor_between, protected
        text = _run_text(run)
        if text is None:
            if any(c.tag in (qn("w:fldChar"), qn("w:instrText")) for c in run):
                protected = protected or "a field"
            if items:
                anchor_seen_after_text = True
            return
        if anchor_seen_after_text and text:
            anchor_between = True
        items.append((run, hyperlink, text))

    for child in paragraph:
        tag = child.tag
        if tag == qn("w:r"):
            add_run(child, None)
        elif tag == qn("w:hyperlink"):
            for inner in child:
                if inner.tag == qn("w:r"):
                    add_run(inner, child)
                elif inner.tag not in _KEPT_IN_PLACE:
                    protected = protected or "a complex hyperlink"
        elif tag == qn("w:fldSimple"):
            # A simple field (e.g. PAGE) stays where it is; the text around it is editable.
            if items:
                anchor_seen_after_text = True
        elif tag in _PROTECTED:
            protected = protected or _PROTECTED[tag]
        elif tag not in _KEPT_IN_PLACE:
            protected = protected or "unsupported content"
    segments: list[Segment] = []
    for run, hyperlink, text in items:
        signature = _signature(run, hyperlink)
        if segments and segments[-1].signature == signature:
            segments[-1].runs.append(run)
            segments[-1].text += text
        else:
            segments.append(Segment([run], text, signature, hyperlink))
    return Unit(index, part, paragraph, segments, protected, anchor_between)


def _parts(document: Any) -> Iterator[tuple[str, Any]]:
    yield "body", document.part.element
    seen: set[str] = set()
    for rel in document.part.rels.values():
        if rel.reltype in (RT.HEADER, RT.FOOTER) and not rel.is_external:
            name = str(rel.target_part.partname)
            if name not in seen:
                seen.add(name)
                kind = "header" if rel.reltype == RT.HEADER else "footer"
                yield kind, rel.target_part.element


def open_docx(data: bytes) -> Any:
    if len(data) > MAX_DOCX_BYTES:
        raise DocxEditError("The Word file is too large to edit.", "too_large")
    if data[:2] != b"PK":
        raise DocxEditError("This is not a Word (.docx) file.", "not_docx")
    try:
        return Document(io.BytesIO(data))
    except Exception as exc:  # python-docx raises several types for damaged files
        raise DocxEditError("The Word file could not be opened (it may be damaged).") from exc


def read_units(document: Any) -> list[Unit]:
    units: list[Unit] = []
    for part, element in _parts(document):
        for paragraph in element.iter(qn("w:p")):
            units.append(_unit(len(units), part, paragraph))
    return units


# --------------------------------------------------------------------------- writing


@dataclass(slots=True)
class Revision:
    author: str = "EZO"
    date: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    next_id: int = 1

    def attrs(self) -> dict[str, str]:
        self.next_id += 1
        return {qn("w:id"): str(self.next_id), qn("w:author"): self.author, qn("w:date"): self.date}


def _set_text(run: Any, text: str, *, deleted: bool = False) -> None:
    for child in list(run):
        if child.tag != qn("w:rPr"):
            run.remove(child)
    tag = qn("w:delText") if deleted else qn("w:t")
    for index, line in enumerate(text.split("\n")):
        if index:
            etree.SubElement(run, qn("w:br"))
        for col, chunk in enumerate(line.split("\t")):
            if col:
                etree.SubElement(run, qn("w:tab"))
            if chunk:
                node = etree.SubElement(run, tag)
                node.text = chunk
                node.set(_XML_SPACE, "preserve")


def _new_run(segment: Segment, text: str, *, deleted: bool = False) -> Any:
    run = copy.deepcopy(segment.runs[0])
    _set_text(run, text, deleted=deleted)
    return run


def _wrap(element: Any, tag: str, revision: Revision) -> Any:
    wrapper = etree.Element(qn(tag), revision.attrs())
    wrapper.append(element)
    return wrapper


def _shell(hyperlink: Any) -> Any:
    clone = copy.deepcopy(hyperlink)
    for child in list(clone):
        clone.remove(child)
    return clone


def _pieces_from_markers(
    unit: Unit, new: str, marks: dict[int, Segment]
) -> list[tuple[str, Segment]] | None:
    """New text split by ⟦k⟧ markers; None when the markers are broken."""
    dominant = unit.dominant
    pieces: list[tuple[str, Segment]] = []
    position = 0
    for match in _MARK.finditer(new):
        k = int(match.group(1))
        if k not in marks:
            return None
        if match.start() > position:
            pieces.append((new[position : match.start()], dominant))
        pieces.append((match.group(2), marks[k]))
        position = match.end()
    pieces.append((new[position:], dominant))
    if any(_ANY_MARK.search(text) for text, _ in pieces):
        return None
    return [(_unescape(t), s) for t, s in pieces if t]


def _pieces_by_diff(unit: Unit, new: str) -> list[tuple[str, Segment]] | None:
    """Map a lightly edited text onto the original segments character by character."""
    old = unit.text
    owner: list[int] = []
    for i, segment in enumerate(unit.segments):
        owner += [i] * len(segment.text)
    matcher = SequenceMatcher(None, old, new, autojunk=False)
    if matcher.ratio() < 0.5:
        return None
    assigned: list[int] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            assigned += owner[i1:i2]
        elif op in ("replace", "insert"):
            source = (
                owner[i1]
                if i1 < len(owner) and op == "replace"
                else (owner[i1 - 1] if i1 > 0 else (owner[0] if owner else 0))
            )
            assigned += [source] * (j2 - j1)
    pieces: list[tuple[str, Segment]] = []
    for char, index in zip(new, assigned, strict=True):
        segment = unit.segments[index]
        if pieces and pieces[-1][1] is segment:
            pieces[-1] = (pieces[-1][0] + char, segment)
        else:
            pieces.append((char, segment))
    return pieces


def _merge(pieces: list[tuple[str, Segment]]) -> list[tuple[str, Segment]]:
    merged: list[tuple[str, Segment]] = []
    for text, segment in pieces:
        if merged and merged[-1][1].signature == segment.signature:
            merged[-1] = (merged[-1][0] + text, merged[-1][1])
        else:
            merged.append((text, segment))
    return merged


def _first_position(unit: Unit) -> Any:
    first = unit.segments[0].runs[0]
    parent = first.getparent()
    return parent if parent.tag == qn("w:hyperlink") else first


def _remove_old(unit: Unit) -> None:
    for segment in unit.segments:
        for run in segment.runs:
            parent = run.getparent()
            parent.remove(run)
            if parent.tag == qn("w:hyperlink") and parent.find(qn("w:r")) is None:
                parent.getparent().remove(parent)


def _insert_before(anchor: Any, elements: list[Any]) -> None:
    for element in elements:
        anchor.addprevious(element)


def _apply(unit: Unit, pieces: list[tuple[str, Segment]], revision: Revision | None) -> None:
    pieces = _merge([(t, s) for t, s in pieces if t])
    anchor = _first_position(unit)
    placeholder = etree.Element(qn("w:proofErr"))  # keeps the position while runs move
    anchor.addprevious(placeholder)
    elements: list[Any] = []
    if revision is not None:
        single = len(unit.segments) == 1 and unit.segments[0].hyperlink is None
        if single and len(pieces) <= 1:
            elements += _word_level(unit, pieces[0][0] if pieces else "", revision)
        else:
            for segment in unit.segments:
                for run in segment.runs:
                    deleted = _new_run(segment, _run_text(run) or "", deleted=True)
                    wrapped = _wrap(deleted, "w:del", revision)
                    if segment.hyperlink is not None:
                        shell = _shell(segment.hyperlink)
                        shell.append(wrapped)
                        wrapped = shell
                    elements.append(wrapped)
            for text, segment in pieces:
                inserted = _wrap(_new_run(segment, text), "w:ins", revision)
                if segment.hyperlink is not None:
                    shell = _shell(segment.hyperlink)
                    shell.append(inserted)
                    inserted = shell
                elements.append(inserted)
    else:
        for text, segment in pieces:
            run = _new_run(segment, text)
            if segment.hyperlink is not None:
                shell = _shell(segment.hyperlink)
                shell.append(run)
                run = shell
            elements.append(run)
    _remove_old(unit)
    _insert_before(placeholder, elements)
    placeholder.getparent().remove(placeholder)


_TOKEN = re.compile(r"\s+|\w+|[^\w\s]", re.UNICODE)


def _word_level(unit: Unit, new: str, revision: Revision) -> list[Any]:
    segment = unit.segments[0]
    old_tokens = _TOKEN.findall(unit.text)
    new_tokens = _TOKEN.findall(new)
    elements: list[Any] = []
    matcher = SequenceMatcher(None, old_tokens, new_tokens, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        old_text, new_text = "".join(old_tokens[i1:i2]), "".join(new_tokens[j1:j2])
        if op == "equal":
            elements.append(_new_run(segment, old_text))
            continue
        if old_text:
            elements.append(_wrap(_new_run(segment, old_text, deleted=True), "w:del", revision))
        if new_text:
            elements.append(_wrap(_new_run(segment, new_text), "w:ins", revision))
    return elements


# --------------------------------------------------------------------------- inventory


def inventory(data: bytes) -> dict[str, Any]:
    """Structural facts used to check that an edit preserved the document."""
    document = open_docx(data)
    elements = [element for _, element in _parts(document)]

    def count(tag: str) -> int:
        return sum(1 for element in elements for _ in element.iter(tag))

    styles_used: Counter[str] = Counter(
        node.get(qn("w:val")) or "" for element in elements for node in element.iter(qn("w:pStyle"))
    )
    counts: dict[str, Any] = {
        "paragraphs": count(qn("w:p")),
        "tables": count(qn("w:tbl")),
        "table_cells": count(qn("w:tc")),
        "images": count("{http://schemas.openxmlformats.org/drawingml/2006/main}blip"),
        "sections": len(document.sections),
        "paragraph_styles": dict(sorted(styles_used.items())),
        "numbered_paragraphs": count(qn("w:numPr")),
        "hyperlinks": count(qn("w:hyperlink")),
        "bookmarks": count(qn("w:bookmarkStart")),
        "comments": count(qn("w:commentRangeStart")),
        "fields": count(qn("w:fldSimple"))
        + sum(
            1
            for element in elements
            for e in element.iter(qn("w:fldChar"))
            if e.get(qn("w:fldCharType")) == "begin"
        ),
        "tracked_changes": count(qn("w:ins")) + count(qn("w:del")),
    }
    parts = list(_parts(document))
    counts["headers"] = sum(1 for kind, _ in parts if kind == "header")
    counts["footers"] = sum(1 for kind, _ in parts if kind == "footer")
    styles = document.part.package.part_related_by(RT.OFFICE_DOCUMENT).part_related_by(RT.STYLES)
    counts["styles_sha256"] = hashlib.sha256(styles.blob).hexdigest()
    section = document.sections[0]
    counts["page_setup"] = {
        "width": section.page_width,
        "height": section.page_height,
        "orientation": int(section.orientation),
        "margins": [
            section.left_margin,
            section.right_margin,
            section.top_margin,
            section.bottom_margin,
        ],
    }
    return counts


def compare_inventory(before: dict[str, Any], after: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(preserved, changed) property names. Tracked changes are expected to grow when
    they were requested."""
    preserved: list[str] = []
    changed: list[str] = []
    for key, value in before.items():
        if key == "tracked_changes":
            continue
        (preserved if after.get(key) == value else changed).append(key)
    return preserved, changed


# --------------------------------------------------------------------------- editing


@dataclass(slots=True)
class EditReport:
    changed: list[int] = field(default_factory=list)
    unchanged: int = 0
    skipped: dict[int, str] = field(default_factory=dict)
    formatting_fallback: list[int] = field(default_factory=list)
    number_changes: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        reasons = Counter(self.skipped.values())
        return {
            "changed_paragraphs": len(self.changed),
            "unchanged_paragraphs": self.unchanged,
            "skipped_paragraphs": {reason: n for reason, n in reasons.items()},
            "formatting_fallback_paragraphs": self.formatting_fallback,
            "paragraphs_with_changed_numbers": self.number_changes,
            "warnings": self.warnings[:30],
        }


_DIGITS = re.compile(r"\d+(?:[.,]\d+)*")


def editable_units(document: Any) -> list[Unit]:
    return [u for u in read_units(document) if u.text.strip()]


def apply_edits(
    data: bytes,
    edits: dict[int, str],
    *,
    tracked: bool = False,
    check_numbers: bool = True,
) -> tuple[bytes, EditReport]:
    """Apply new paragraph texts (keyed by unit index, as produced by `prepare_edit`).

    `edits` values may carry ⟦k⟧ markers (from `Unit.encode`). Returns the new file and
    a report; the input bytes are never modified."""
    document = open_docx(data)
    units = read_units(document)
    report = EditReport()
    revision = Revision(next_id=_max_id(document) + 1) if tracked else None
    for unit in units:
        if unit.index not in edits or not unit.text.strip():
            continue
        if unit.protected:
            report.skipped[unit.index] = unit.protected
            continue
        raw = edits[unit.index]
        _, unit_marks = unit.encode()
        plain = _unescape(_ANY_MARK.sub("", raw))
        pieces = (
            _pieces_from_markers(unit, raw, unit_marks)
            if unit_marks and _MARK.search(raw)
            else None
        )
        if pieces is None and unit_marks:
            # Markers missing or broken: map small edits character by character.
            pieces = _pieces_by_diff(unit, plain)
            if pieces is None:
                report.formatting_fallback.append(unit.index)
        if pieces is None:
            pieces = [(plain, unit.dominant)]
        new_text = "".join(t for t, _ in pieces)
        if new_text == unit.text:
            report.unchanged += 1
            continue
        if check_numbers and sorted(_DIGITS.findall(unit.text)) != sorted(
            _DIGITS.findall(new_text)
        ):
            report.number_changes.append(unit.index)
        if unit.has_anchor_between_text:
            report.warnings.append(
                f"Paragraph {unit.index + 1}: an inline object (image or note mark) now follows "
                "the edited text instead of sitting inside it."
            )
        _apply(unit, pieces, revision)
        report.changed.append(unit.index)
    if report.formatting_fallback:
        report.warnings.append(
            f"{len(report.formatting_fallback)} paragraph(s) lost their mixed inline formatting "
            "(e.g. one bold word) and now use the paragraph's main formatting."
        )
    if report.skipped:
        report.warnings.append(
            f"{len(report.skipped)} paragraph(s) were not changed because they contain "
            + ", ".join(sorted(set(report.skipped.values())))
            + "."
        )
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue(), report


def _max_id(document: Any) -> int:
    best = 0
    for _, element in _parts(document):
        for node in element.iter():
            value = node.get(qn("w:id"))
            if value and value.lstrip("-").isdigit():
                best = max(best, int(value))
    return best


def replace_text(
    data: bytes, old: str, new: str, *, tracked: bool = False, ignore_case: bool = False
) -> tuple[bytes, EditReport, int]:
    """Deterministic find-and-replace that keeps formatting, also when the text to find
    spans several runs. Returns (file, report, number of replacements)."""
    if not old:
        raise DocxEditError("Nothing to search for.", "bad_input")
    pattern = re.compile(re.escape(old), re.IGNORECASE if ignore_case else 0)
    document = open_docx(data)
    edits: dict[int, str] = {}
    count = 0
    for unit in read_units(document):
        hits = len(pattern.findall(unit.text))
        if hits:
            count += hits
            edits[unit.index] = _escape(pattern.sub(lambda _: new, unit.text))
    if not edits:
        return data, EditReport(), 0
    # Plain new texts (no markers): runs are mapped by difflib, so only the replaced
    # characters change formatting ownership.
    result, report = _apply_plain(data, edits, tracked=tracked)
    return result, report, count


def _apply_plain(data: bytes, edits: dict[int, str], *, tracked: bool) -> tuple[bytes, EditReport]:
    document = open_docx(data)
    report = EditReport()
    revision = Revision(next_id=_max_id(document) + 1) if tracked else None
    for unit in read_units(document):
        if unit.index not in edits:
            continue
        if unit.protected:
            report.skipped[unit.index] = unit.protected
            continue
        plain = _unescape(edits[unit.index])
        pieces = _pieces_by_diff(unit, plain) or [(plain, unit.dominant)]
        _apply(unit, pieces, revision)
        report.changed.append(unit.index)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue(), report


def docx_text(data: bytes) -> str:
    """Plain text of the body paragraphs (for previews and follow-up edits)."""
    document = open_docx(data)
    return "\n\n".join(u.text for u in read_units(document) if u.part == "body" and u.text.strip())
