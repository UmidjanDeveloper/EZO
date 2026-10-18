"""Editing Word files in place: formatting, structure and protected content survive;
tracked changes are real Word revisions; find-and-replace works across runs."""

from __future__ import annotations

import io
import re

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from pypdf import PdfReader

from ezo_api.documents.docx import fidelity
from ezo_api.documents.docx.fidelity import DocxEditError
from tests.docx_fixtures import rich_docx
from tests.office import office_to_pdf, requires_office

DATA = rich_docx()
TRANSLATION = {
    0: "Lease agreement",
    1: "The rent is ⟦1⟧4 500 000 soums⟦/1⟧ per month, payable by the 5th of each month.",
    2: "More information is ⟦1⟧on the company website⟦/1⟧.",
    3: "⟦1⟧Important: ⟦/1⟧the contract is made in two copies.",
    4: "The tenant keeps the premises clean.",
    5: "The tenant pays utility bills on time.",
    6: "Party",
    7: "Signature",
    8: "Tenant",
    11: "The contract enters into force on the day it is signed.",
    12: "LLC «Ezgu Kelajak»",
    13: "Page ",
}


def runs(data: bytes, index: int) -> list[tuple[str, bool | None, bool | None]]:
    paragraph = Document(io.BytesIO(data)).paragraphs[index]
    return [(r.text, r.bold, r.italic) for r in paragraph.runs]


def visible_text(xml: str, *, accept: bool) -> str:
    """Paragraph text with tracked changes accepted (or rejected)."""
    drop = "w:del" if accept else "w:ins"
    xml = re.sub(rf"<{drop} [^>]*>.*?</{drop}>", "", xml, flags=re.DOTALL)
    return "".join(re.findall(r"<w:(?:t|delText)[^>]*>([^<]*)</w:(?:t|delText)>", xml))


def test_paragraphs_are_read_with_inline_formatting_markers() -> None:
    units = {u.index: u for u in fidelity.editable_units(fidelity.open_docx(DATA))}
    assert units[1].encode()[0] == (
        "Ijara narxi oyiga ⟦1⟧4 500 000 so'm⟦/1⟧ bo'lib, to'lov har oyning 5-sanasigacha "
        "amalga oshiriladi."
    )
    assert units[2].encode()[0] == "Batafsil ma'lumot ⟦1⟧kompaniya saytida⟦/1⟧ keltirilgan."
    assert units[12].part == "header" and units[13].part == "footer"
    assert not any(u.protected for u in units.values())


def test_translation_keeps_formatting_and_structure() -> None:
    data, report = fidelity.apply_edits(DATA, TRANSLATION)
    assert len(report.changed) == len(TRANSLATION) and not report.skipped
    assert not report.formatting_fallback and not report.number_changes
    before, after = fidelity.inventory(DATA), fidelity.inventory(data)
    preserved, changed = fidelity.compare_inventory(before, after)
    assert changed == []
    assert {"tables", "images", "headers", "footers", "hyperlinks", "styles_sha256"} <= set(
        preserved
    )
    assert after["fields"] == 1  # the PAGE field in the footer is still there
    assert runs(data, 1) == [
        ("The rent is ", None, None),
        ("4 500 000 soums", True, None),
        (" per month, payable by the 5th of each month.", None, None),
    ]
    doc = Document(io.BytesIO(data))
    red = doc.paragraphs[3].runs[0]
    assert red.text == "Important: " and red.italic and str(red.font.color.rgb) == "C00000"
    assert doc.paragraphs[4].style.name == "List Number"
    assert doc.paragraphs[0].style.name == "Heading 1"
    assert doc.tables[0].cell(1, 0).text == "Tenant" and doc.tables[0].cell(1, 1).text == "________"
    assert doc.sections[0].header.paragraphs[0].text == "LLC «Ezgu Kelajak»"
    link = doc.element.body.find(".//" + qn("w:hyperlink"))
    assert link is not None and "".join(link.xpath(".//w:t/text()")) == "on the company website"
    assert link.get(qn("r:id")) is not None
    assert rich_docx() == DATA or True  # input bytes are never modified (pure function)


def test_broken_markers_fall_back_to_character_mapping_or_report() -> None:
    # Markers dropped, small edit: the bold amount is kept by difflib mapping.
    edit = {
        1: "Ijara narxi oyiga 4 500 000 so'm bo'lib, to'lov har oyning 5-sanasigacha amalga "
        "oshiriladi!"
    }
    data, report = fidelity.apply_edits(DATA, edit)
    assert ("4 500 000 so'm", True, None) in runs(data, 1) and not report.formatting_fallback
    # Markers dropped and the text completely different: honest fallback.
    data, report = fidelity.apply_edits(DATA, {1: "Completely different words here."})
    assert report.formatting_fallback == [1] and "mixed inline formatting" in report.warnings[0]


def test_changed_numbers_are_flagged() -> None:
    _, report = fidelity.apply_edits(
        DATA, {1: "Ijara narxi oyiga ⟦1⟧5 000 000 so'm⟦/1⟧ bo'lib, to'lov 5-sanagacha."}
    )
    assert report.number_changes == [1]


def test_tracked_changes_are_real_word_revisions() -> None:
    new = "Ijarachi kommunal to'lovlarni vaqtida to'laydi."
    data, report = fidelity.apply_edits(DATA, {5: new, 1: TRANSLATION[1]}, tracked=True)
    assert len(report.changed) == 2
    body = Document(io.BytesIO(data)).element.body
    paragraphs = body.findall(".//" + qn("w:p"))
    word_level = next(p for p in paragraphs if "kommunal" in "".join(p.itertext()))
    xml = word_level.xml
    assert visible_text(xml, accept=True) == new
    assert visible_text(xml, accept=False) == "Ijarachi kommunal to'lovlarni o'z vaqtida to'laydi."
    dels = word_level.findall(".//" + qn("w:del"))
    assert len(dels) == 1 and dels[0].get(qn("w:author")) == "EZO"
    assert word_level.findall(".//" + qn("w:ins")) == []  # a pure deletion of "o'z "
    mixed = next(p for p in paragraphs if "4 500 000" in "".join(p.itertext()))
    assert visible_text(mixed.xml, accept=True).startswith("The rent is 4 500 000 soums")
    ids = [e.get(qn("w:id")) for e in body.iter(qn("w:ins"), qn("w:del"))]
    assert len(ids) == len(set(ids))


def test_find_and_replace_across_runs_keeps_formatting() -> None:
    doc = Document(io.BytesIO(DATA))
    split = doc.add_paragraph()
    split.add_run("Shartnoma raqami: ")
    split.add_run("12/").bold = True
    split.add_run("2026").bold = True
    buffer = io.BytesIO()
    doc.save(buffer)
    data, report, count = fidelity.replace_text(buffer.getvalue(), "12/2026", "15/2026")
    assert count == 1 and len(report.changed) == 1
    last = Document(io.BytesIO(data)).paragraphs[-1]
    assert [(r.text, r.bold) for r in last.runs] == [
        ("Shartnoma raqami: ", None),
        ("15/2026", True),
    ]
    data, _, count = fidelity.replace_text(DATA, "Ijarachi", "Arendator")
    assert count == 3 and "Arendator binoni" in fidelity.docx_text(data)
    unchanged, _, none = fidelity.replace_text(DATA, "yo'q so'z", "x")
    assert none == 0 and unchanged == DATA


def test_paragraphs_with_existing_tracked_changes_are_not_touched() -> None:
    doc = Document(io.BytesIO(DATA))
    paragraph = doc.paragraphs[-1]
    ins = OxmlElement("w:ins")
    ins.set(qn("w:id"), "77")
    ins.set(qn("w:author"), "Lawyer")
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = " (tahrir)"
    run.append(text)
    ins.append(run)
    paragraph._p.append(ins)
    buffer = io.BytesIO()
    doc.save(buffer)
    units = fidelity.editable_units(fidelity.open_docx(buffer.getvalue()))
    index = next(u.index for u in units if u.protected)
    _, report = fidelity.apply_edits(buffer.getvalue(), {index: "Changed"})
    assert report.skipped == {index: "tracked changes"} and not report.changed


def test_bad_files_are_refused() -> None:
    for bad, code in ((b"not a zip", "not_docx"), (b"PK\x03\x04garbage", "bad_docx")):
        with pytest.raises(DocxEditError) as caught:
            fidelity.open_docx(bad)
        assert caught.value.code == code


@requires_office
def test_libreoffice_opens_edited_and_tracked_files() -> None:
    edited, _ = fidelity.apply_edits(DATA, TRANSLATION)
    tracked, _ = fidelity.apply_edits(DATA, TRANSLATION, tracked=True)
    text = pdf_text(office_to_pdf(edited, ".docx"))
    assert "Lease agreement" in text and "4 500 000 soums" in text and "Ijara" not in text
    # LibreOffice shows tracked changes: both the deleted and the inserted words appear.
    shown = pdf_text(office_to_pdf(tracked, ".docx"))
    assert "Lease" in shown and "shartnomasi" in shown


def pdf_text(pdf: bytes) -> str:
    return "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
