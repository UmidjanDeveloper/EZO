"""Fixed data-only entry point. No API, database, provider or tool access."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import unicodedata
from pathlib import Path

from ezo_api.documents.executor.epub import parse_epub
from ezo_api.documents.executor.protocol import (
    MAX_INPUT_BYTES,
    MAX_OUTPUT_BYTES,
    MAX_TEXT_CHARS,
    MEMORY_BYTES,
    PIDS,
    ExtractionRequest,
    ExtractionResult,
    SourceSection,
)
from ezo_api.knowledge.parsers.office import parse_docx
from ezo_api.knowledge.parsers.pdf import parse_pdf


def verify_boundary() -> None:
    status = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )
    if os.getuid() != 10001 or status["NoNewPrivs"].strip() != "1":
        raise RuntimeError("isolation_unavailable")
    if any(int(status[key].strip(), 16) for key in ("CapEff", "CapBnd", "CapAmb")):
        raise RuntimeError("isolation_unavailable")
    controls = {"memory.max": MEMORY_BYTES, "memory.swap.max": 0, "pids.max": PIDS}
    for name, expected in controls.items():
        if int(Path("/sys/fs/cgroup", name).read_text()) != expected:
            raise RuntimeError("isolation_unavailable")
    quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
    if quota == "max" or int(quota) > int(period):
        raise RuntimeError("isolation_unavailable")
    if set(os.listdir("/sys/class/net")) != {"lo"}:
        raise RuntimeError("isolation_unavailable")
    root = next(
        line.split()
        for line in Path("/proc/self/mountinfo").read_text().splitlines()
        if line.split()[4] == "/"
    )
    if "ro" not in root[5].split(","):
        raise RuntimeError("isolation_unavailable")


def main() -> int:
    try:
        verify_boundary()
        request = ExtractionRequest.model_validate_json(sys.stdin.buffer.read(7 * 1024 * 1024 + 1))
        data = base64.b64decode(request.data_base64, validate=True)
        if len(data) > MAX_INPUT_BYTES:
            raise ValueError("input_limit")
        if request.format == "epub":
            parsed = parse_epub(data)
        elif request.format == "docx":
            parsed = parse_docx(data, "document.docx")
        else:
            parsed = parse_pdf(data, "document.pdf")
        parts: list[str] = []
        sections: list[SourceSection] = []
        offset = 0
        members = parsed.metadata.get("section_sources", [])
        for index, section in enumerate(parsed.sections):
            text = unicodedata.normalize("NFC", section.text).strip()
            if not text:
                continue
            if parts:
                offset += 2
            end = offset + len(text)
            if end > MAX_TEXT_CHARS:
                raise ValueError("output_limit")
            sections.append(
                SourceSection(
                    start=offset,
                    end=end,
                    page=section.page,
                    heading=section.heading,
                    member=members[index] if members else None,
                )
            )
            parts.append(text)
            offset = end
        result = ExtractionResult(
            source_sha256=hashlib.sha256(data).hexdigest(),
            text="\n\n".join(parts),
            sections=sections,
            needs_ocr=parsed.needs_ocr,
        )
        output = result.model_dump_json().encode()
        if len(output) > MAX_OUTPUT_BYTES:
            raise ValueError("output_limit")
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        # Native libraries can put private paths/text into their exception strings.
        sys.stderr.write(json.dumps({"code": "invalid_document_or_resource_limit"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
