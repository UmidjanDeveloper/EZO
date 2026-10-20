"""Bound OOXML expansion and tree complexity before any materializing parser.

A preflight, not a parser sandbox. No extraction or relationship resolution occurs.
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import iterparse

MAX_XML_BYTES = 8 * 1024 * 1024
MAX_TOTAL_XML_BYTES = 32 * 1024 * 1024
MAX_ENTRIES = 5000
MAX_EXPANDED_BYTES = 200 * 1024 * 1024
MAX_ELEMENTS = 100_000
MAX_PARAGRAPHS = 20_000
MAX_DEPTH = 64
MAX_COLUMNS = 256
MAX_ROWS = 20_000
MAX_SHEETS = 64


class OfficeInputLimit(Exception):
    def __init__(self, message: str, code: str = "too_complex") -> None:
        self.code = code
        super().__init__(message)


def _check_reference(value: str) -> None:
    for reference in value.split(":"):
        match = re.fullmatch(r"\$?([A-Za-z]+)\$?([0-9]+)", reference)
        if match is None:
            raise OfficeInputLimit("The spreadsheet has invalid cell references.", "corrupt")
        column = 0
        for letter in match[1].upper():
            column = column * 26 + ord(letter) - ord("A") + 1
        if column > MAX_COLUMNS or int(match[2]) > MAX_ROWS:
            raise OfficeInputLimit("The spreadsheet dimensions are too complex to read safely.")


def validate_ooxml(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES or len({x.filename for x in infos}) != len(infos):
                raise OfficeInputLimit("The Office archive has too many or duplicate parts.")
            if sum(x.file_size for x in infos) > MAX_EXPANDED_BYTES:
                raise OfficeInputLimit(
                    "The Office archive is too large when expanded.", "too_large"
                )
            xmls = [x for x in infos if x.filename.lower().endswith((".xml", ".rels"))]
            if (
                any(x.file_size > MAX_XML_BYTES for x in xmls)
                or sum(x.file_size for x in xmls) > MAX_TOTAL_XML_BYTES
            ):
                raise OfficeInputLimit(
                    "The Office XML data is too large to parse safely.", "too_large"
                )
            elements = paragraphs = sheets = logical_cells = 0
            for info in xmls:
                with archive.open(info) as stream:
                    # ZIP's reader checks size/CRC; a bounded read also caps actual expansion.
                    xml = stream.read(MAX_XML_BYTES + 1)
                if len(xml) > MAX_XML_BYTES:
                    raise OfficeInputLimit("The Office XML data is too large.", "too_large")
                stack = []
                for event, element in iterparse(
                    io.BytesIO(xml),
                    events=("start", "end"),
                    forbid_dtd=True,
                    forbid_entities=True,
                    forbid_external=True,
                ):
                    if event == "start":
                        stack.append(element)
                        elements += 1
                        name = element.tag.rsplit("}", 1)[-1]
                        paragraphs += name == "p"
                        sheets += name == "sheet"
                        if (
                            elements > MAX_ELEMENTS
                            or paragraphs > MAX_PARAGRAPHS
                            or sheets > MAX_SHEETS
                            or len(stack) > MAX_DEPTH
                        ):
                            raise OfficeInputLimit(
                                "The Office document is too complex to parse safely."
                            )
                        if name in ("gridSpan", "gridBefore", "gridAfter"):
                            span = int(next(iter(element.attrib.values()), "1"))
                            logical_cells += span
                            if span < 0 or span > MAX_COLUMNS or logical_cells > MAX_ELEMENTS:
                                raise OfficeInputLimit(
                                    "The Word table is too complex to parse safely."
                                )
                        if info.filename.startswith("xl/"):
                            if name == "dimension" and element.get("ref"):
                                _check_reference(element.attrib["ref"])
                            if name == "c" and element.get("r"):
                                _check_reference(element.attrib["r"])
                            if name == "row" and int(element.get("r", "1")) > MAX_ROWS:
                                raise OfficeInputLimit("The spreadsheet has too many rows.")
                    else:
                        stack.pop()
                        element.clear()
                        if stack:
                            stack[-1].remove(element)
    except (
        zipfile.BadZipFile,
        ParseError,
        DefusedXmlException,
        ValueError,
        RuntimeError,
        NotImplementedError,
        OSError,
    ) as exc:
        raise OfficeInputLimit(
            "The Office XML or archive is unsafe or damaged.", "corrupt"
        ) from exc
