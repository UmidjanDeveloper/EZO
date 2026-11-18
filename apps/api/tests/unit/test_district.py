"""District center helpers: table headers, phones, pace and name matching."""

from __future__ import annotations

import io
from datetime import date

import pytest
from openpyxl import Workbook

from ezo_api.db.models import DistrictMember, DistrictProject
from ezo_api.district.progress import compute
from ezo_api.district.records import RecordsError, from_api, from_table, phone_of
from ezo_api.district.service import match_people, match_projects, notice_text


def test_xlsx_with_cyrillic_headers_and_a_title_row() -> None:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["Хатлов ҳисоботи"])
    sheet.append(["Ф.И.Ш", "Телефон", "Махалла", "Режа", "Бажарилди"])
    sheet.append(["Алиев Ботир", "901112233", "Навбаҳор", 120, "45"])
    buffer = io.BytesIO()
    book.save(buffer)
    [record] = from_table(buffer.getvalue(), "hisobot.xlsx")
    assert (record.name, record.phone, record.area, record.target, record.done) == (
        "Алиев Ботир", "998901112233", "Навбаҳор", 120.0, 45.0,
    )  # fmt: skip


def test_a_table_without_the_needed_columns_is_refused() -> None:
    with pytest.raises(RecordsError):
        from_table(b"a,b,c\n1,2,3\n", "x.csv")


@pytest.mark.parametrize(
    ("raw", "phone"),
    [("+998 (90) 123-45-67", "998901234567"), ("90 123 45 67", "998901234567"), ("12345", None)],
)
def test_phone_of(raw: str, phone: str | None) -> None:
    assert phone_of(raw) == phone


def test_api_records_with_dotted_paths() -> None:
    body = {"result": [{"user": {"name": "Aliyev B."}, "stats": {"plan": "10", "done": 3}}]}
    [record] = from_api(
        body, "result", {"name": "user.name", "target": "stats.plan", "done": "stats.done"}
    )
    assert (record.name, record.target, record.done) == ("Aliyev B.", 10.0, 3.0)
    with pytest.raises(RecordsError):
        from_api({"result": {}}, "result", {"name": "x"})


def test_pace_marks_late_starters_and_slow_people() -> None:
    status = compute(
        name="Xatlov", unit="xonadon", start=date(2026, 11, 1), deadline=date(2026, 11, 21),
        today=date(2026, 11, 11),
        rows=[("1", "A", "", 100, 0), ("2", "B", "", 100, 30), ("3", "C", "", 100, 45)],
    )  # fmt: skip
    assert status.expected_share == 0.5 and status.days_left == 10
    assert [p.name for p in status.behind] == ["A", "B"]  # C did 45 ≥ 0.8 × 50


def test_projects_and_people_are_found_by_their_words() -> None:
    xatlov = DistrictProject(name="Xatlov 2026", aliases=["uy-joy ro'yxati"])
    bandlik = DistrictProject(name="Bandlik dasturi", aliases=[])
    assert match_projects("xatlov qalay ketyapti?", [xatlov, bandlik]) == [xatlov]
    assert match_projects("Bandlik bo'yicha hisobot", [xatlov, bandlik]) == [bandlik]
    aliyev = DistrictMember(full_name="Aliyev Botir")
    karimova = DistrictMember(full_name="Karimova Dilnoza")
    assert match_people("Aliyevni ogohlantir", [aliyev, karimova]) == [aliyev]
    assert match_people("Karimovaga sms yubor", [aliyev, karimova]) == [karimova]


def test_notice_text() -> None:
    text = notice_text(name="Aliyev Botir", project_name="Xatlov 2026", unit="xonadon",
                       target=100, done=5, sender="Xatirchi tumani hokimi")  # fmt: skip
    assert text.startswith("Hurmatli Aliyev Botir! «Xatlov 2026» bo‘yicha rejangiz 100 xonadon")
    assert text.endswith("— Xatirchi tumani hokimi")
