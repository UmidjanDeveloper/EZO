"""Progress records from outside EZO: an Excel/CSV table or an official JSON API.

Both become the same `Record` (a person, their plan and their done count). Column and field
names differ between offices, so headers are recognised in Uzbek (Latin and Cyrillic),
Russian and English, and an API source names its own fields in the project settings.
Every value is data, never an instruction.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Any

from ezo_api.core.text import normalize

MAX_ROWS = 5_000


class RecordsError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class Record:
    name: str
    target: float | None = None
    done: float | None = None
    phone: str | None = None
    area: str = ""
    position: str = ""
    external_id: str | None = None


_HEADERS: dict[str, tuple[str, ...]] = {
    "name": ("f.i.sh", "fish", "fio", "ф.и.ш", "ф.и.о", "фио", "ism", "ismi", "mas'ul", "masul",
             "xodim", "full name", "name", "имя", "ходим", "масъул", "ijrochi", "исполнитель"),
    "phone": ("telefon", "tel", "phone", "телефон", "тел", "mobile", "raqam"),
    "area": ("mahalla", "mfy", "hudud", "sektor", "махалла", "ҳудуд", "район", "area", "участок"),
    "position": ("lavozim", "lavozimi", "position", "должность", "лавозим"),
    "target": ("reja", "plan", "rejada", "jami", "target", "план", "режа", "вазифа", "vazifa"),
    "done": ("bajarildi", "bajarilgan", "bajarilgani", "done", "fakt", "fact", "qilingan",
             "xatlov qilingan", "выполнено", "факт", "бажарилди", "бажарилган"),
    "external_id": ("id", "kod", "code", "jshshir", "pinfl", "табельный", "код"),
}  # fmt: skip


def phone_of(value: Any) -> str | None:
    """An Uzbek mobile number as 998XXXXXXXXX, or None."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 9:
        digits = "998" + digits
    return digits if len(digits) == 12 and digits.startswith("998") else None


def number_of(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().replace(" ", "").replace(" ", "").replace(",", ".")
    text = text.rstrip("%")
    try:
        return float(text)
    except ValueError:
        return None


def _field_of(header: Any) -> str | None:
    norm = normalize(str(header or "")).strip(" :*.")
    if not norm:
        return None
    for field_name, names in _HEADERS.items():
        if norm in names:
            return field_name
    for field_name, names in _HEADERS.items():
        if any(len(n) > 3 and n in norm for n in names):
            return field_name
    return None


def _records(rows: list[list[Any]]) -> list[Record]:
    header_at, mapping = -1, {}
    for index, row in enumerate(rows[:10]):
        found = {i: f for i, cell in enumerate(row) if (f := _field_of(cell))}
        if "name" in found.values() and ({"done", "target"} & set(found.values())):
            header_at, mapping = index, found
            break
    if header_at < 0:
        raise RecordsError(
            "no_header",
            "The table needs a header row with a name column (F.I.Sh / Ism) and a plan "
            "(Reja) or done (Bajarildi) column.",
        )
    out: list[Record] = []
    for row in rows[header_at + 1 : header_at + 1 + MAX_ROWS]:
        values: dict[str, Any] = {}
        for i, field_name in mapping.items():
            if i < len(row) and field_name not in values:
                values[field_name] = row[i]
        name = " ".join(str(values.get("name") or "").split())[:160]
        if not name or normalize(name) in ("jami", "итого", "всего", "total"):
            continue
        out.append(
            Record(
                name=name,
                target=number_of(values.get("target")),
                done=number_of(values.get("done")),
                phone=phone_of(values.get("phone")),
                area=" ".join(str(values.get("area") or "").split())[:160],
                position=" ".join(str(values.get("position") or "").split())[:160],
                external_id=(str(values["external_id"]).strip()[:80] or None)
                if values.get("external_id") not in (None, "")
                else None,
            )
        )
    return out


def from_table(data: bytes, filename: str) -> list[Record]:
    """Records from an .xlsx or .csv file."""
    lowered = filename.lower()
    if lowered.endswith(".xlsx"):
        from openpyxl import load_workbook

        try:
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:  # openpyxl raises many types for broken files
            raise RecordsError("bad_file", "The Excel file could not be read.") from exc
        sheet = workbook.worksheets[0]
        rows = [list(r) for r in sheet.iter_rows(values_only=True, max_row=MAX_ROWS + 10)]
        workbook.close()
        return _records(rows)
    if lowered.endswith(".csv"):
        text = data.decode("utf-8-sig", errors="replace")
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t") if text.strip() else None
        reader = (
            csv.reader(io.StringIO(text), dialect) if dialect else csv.reader(io.StringIO(text))
        )
        return _records([row for _, row in zip(range(MAX_ROWS + 10), reader, strict=False)])
    raise RecordsError("unsupported", "Upload an .xlsx or .csv file.")


def _path(item: Any, path: str) -> Any:
    for part in [p for p in path.split(".") if p]:
        if isinstance(item, dict):
            item = item.get(part)
        elif isinstance(item, list) and part.isdigit() and int(part) < len(item):
            item = item[int(part)]
        else:
            return None
    return item


def from_api(body: Any, items_path: str, fields: dict[str, str]) -> list[Record]:
    """Records from an API's JSON body. `fields` maps name/target/done/phone/area/position/
    external_id to dotted paths inside each item."""
    items = _path(body, items_path) if items_path else body
    if not isinstance(items, list):
        raise RecordsError("bad_api_shape", f"The API answer has no list at «{items_path or '.'}».")
    if not fields.get("name"):
        raise RecordsError("bad_mapping", "The API field mapping needs at least “name”.")
    out: list[Record] = []
    for item in items[:MAX_ROWS]:

        def get(key: str, item: Any = item) -> Any:
            path = fields.get(key)
            return _path(item, path) if path else None

        name = " ".join(str(get("name") or "").split())[:160]
        if not name:
            continue
        external = get("external_id")
        out.append(
            Record(
                name=name,
                target=number_of(get("target")),
                done=number_of(get("done")),
                phone=phone_of(get("phone")),
                area=" ".join(str(get("area") or "").split())[:160],
                position=" ".join(str(get("position") or "").split())[:160],
                external_id=str(external).strip()[:80] if external not in (None, "") else None,
            )
        )
    return out
