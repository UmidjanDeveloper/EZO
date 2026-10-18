"""Natural-language PDF requests (uz / ru / en) → ordered steps, without a model."""

from __future__ import annotations

import pytest

from ezo_api.documents.pdf.requests import PdfStep, parse_pdf_request

CASES: list[tuple[str, list[dict[str, object]]]] = [
    (
        "Shu 4 ta PDFni birlashtir va oxirgi betini olib tashla",
        [{"op": "merge"}, {"op": "delete", "pages": "last"}],
    ),
    (
        "4-betni o'chir, 6-betni birinchi betga ko'chir",
        [{"op": "delete", "pages": "4"}, {"op": "move", "pages": "6", "to": 1}],
    ),
    ("2, 3 va 5-betlarni o'chir", [{"op": "delete", "pages": "2,3,5"}]),
    ("1-3 betlarni ajratib ol", [{"op": "extract", "pages": "1-3"}]),
    ("har 2 betni alohida qil", [{"op": "split", "every": 2}]),
    ("2-betni 90 daraja bur", [{"op": "rotate", "pages": "2", "degrees": 90}]),
    ("chapga bur", [{"op": "rotate", "degrees": 270}]),
    ("sahifa raqamlarini qo'y", [{"op": "page_numbers"}]),
    ('suv belgisi "MAXFIY" qo\'y', [{"op": "watermark", "text": "MAXFIY"}]),
    ('pastki qismiga "Hisobot 2026" yoz', [{"op": "header_footer", "footer": "Hisobot 2026"}]),
    ("hajmini kamaytir", [{"op": "compress"}]),
    ("metama'lumotlarini tozala", [{"op": "clean_metadata"}]),
    ("rasmga aylantir", [{"op": "to_images"}]),
    ("nechta betdan iborat?", [{"op": "inspect"}]),
    ("Удали страницу 3", [{"op": "delete", "pages": "3"}]),
    ("Переставь страницу 5 на 1", [{"op": "move", "pages": "5", "to": 1}]),
    ("Merge these PDFs and remove page 2", [{"op": "merge"}, {"op": "delete", "pages": "2"}]),
]


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_requests_become_ordered_steps(text: str, expected: list[dict[str, object]]) -> None:
    assert [s.model_dump(exclude_none=True) for s in parse_pdf_request(text)] == expected


@pytest.mark.parametrize(
    "text", ["PDFni Word ga aylantir", "Salom, qalaysan?", "Bu hujjat nima haqida?"]
)
def test_other_requests_are_left_alone(text: str) -> None:
    assert parse_pdf_request(text) == []


def test_steps_are_validated() -> None:
    for bad in (
        {"op": "delete"},
        {"op": "move", "pages": "2"},
        {"op": "rotate", "degrees": 45},
        {"op": "delete", "pages": "2; rm -rf"},
        {"op": "watermark"},
    ):
        with pytest.raises(ValueError):
            PdfStep.model_validate(bad)
