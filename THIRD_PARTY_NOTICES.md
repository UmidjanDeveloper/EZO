# Third-party notices

EZO's own source code does not contain copied code from the projects reviewed in
[`docs/OPEN_SOURCE_AUDIT.md`](docs/OPEN_SOURCE_AUDIT.md):

- APEX-UI
- VoiceStudio
- OpenMontage
- REA
- open-higgsfield
- Ruflo (audited; optional external MCP orchestrator, not installed, no code copied)

Projects that EZO only studied for ideas are not listed here. Optional external
services such as VoiceStudio and OpenMontage are installed and run separately, under
their own licences, and are not distributed with EZO.

## Bundled fonts

`apps/api/src/ezo_api/documents/fonts/` contains **Liberation Sans** Regular and Bold
(copyright © 2012 Red Hat, Inc., with Reserved Font Name *Liberation*), distributed under the
**SIL Open Font License 1.1**. The full licence text is in
[`apps/api/src/ezo_api/documents/fonts/OFL.txt`](apps/api/src/ezo_api/documents/fonts/OFL.txt).
The fonts are used unmodified to measure text and to draw PDFs and slide previews. They are
not sold on their own.

## System tools used at runtime

Installed as operating-system packages (Docker image, CI), not vendored in this
repository and not linked into EZO's code; EZO runs them as separate processes.

| Tool | License | Use |
| --- | --- | --- |
| Tesseract OCR 5 (`tesseract-ocr`) | Apache-2.0 | OCR of scans and photos |
| tessdata language packs (`tesseract-ocr-uzb`, `-uzb-cyrl`, `-rus`, `-eng`, `-osd`) | Apache-2.0 | recognition models |
| LibreOffice Writer + Calc (`libreoffice-writer-nogui`, `libreoffice-calc-nogui`) | MPL-2.0 | Word/Excel → PDF |
| Liberation fonts, DejaVu fonts (`fonts-liberation`, `fonts-dejavu-core`) | SIL OFL 1.1; Bitstream Vera / public-domain changes | Latin + Cyrillic glyphs for converted PDFs |

## Package dependencies

EZO installs the following direct dependencies through `uv` and `pnpm`. They are not
vendored in this repository. Each package keeps its own copyright and licence, which
ship inside the installed package. The licence values below are read from each
installed package's metadata (2026-10-17).

### API (Python)

| Package | Version | Licence |
|---|---|---|
| fastapi | 0.143.3 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| pydantic / pydantic-settings | 2.14.1 / 2.16.0 | MIT |
| sqlalchemy | 2.1.5 | MIT |
| alembic | 1.20.0 | MIT |
| psycopg | 3.3.6 | LGPL-3.0-only (used unmodified as a library) |
| aiosqlite | 0.22.1 | MIT |
| pgvector | 0.5.1 | MIT |
| anthropic | 1.15.0 | MIT |
| openai | 3.33.0 | Apache-2.0 |
| google-genai | 2.31.0 | Apache-2.0 |
| httpx | 0.28.1 | BSD-3-Clause |
| anyio | 4.15.1 | MIT |
| numpy | 2.5.4 | BSD-3-Clause (with bundled MIT/0BSD/Zlib parts) |
| pypdf | 6.21.1 | BSD-3-Clause |
| pypdfium2 | 5.14.0 | BSD-3-Clause OR Apache-2.0 (bundles PDFium: BSD-3-Clause / Apache-2.0) — page rendering; PyMuPDF was not used because it is AGPL-3.0 |
| python-docx | 1.2.0 | MIT |
| openpyxl | 3.1.5 | MIT |
| trafilatura | 2.3.1 | Apache-2.0 |
| python-pptx | 1.0.2 | MIT |
| pillow | 13.0.0 | MIT-CMU (HPND) |
| reportlab | 5.0.1 | BSD-3-Clause |
| lxml (via python-docx / python-pptx) | 6.1.3 | BSD-3-Clause |
| XlsxWriter (installed by python-pptx; EZO itself writes XLSX with openpyxl) | 3.2.9 | BSD-2-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| tzdata | 2026.5 | Apache-2.0 |

### Web (JavaScript)

| Package | Version | Licence |
|---|---|---|
| next | 16.4.2 | MIT |
| react / react-dom | 19.3.1 | MIT |
| framer-motion | 14.3.0 | MIT |
| lucide-react | 1.59.0 | ISC |
| react-markdown | 10.1.0 | MIT |
| remark-gfm | 4.0.1 | MIT |

When third-party source code is copied into EZO, its required copyright and
licence notice is added to this file in the same commit.
