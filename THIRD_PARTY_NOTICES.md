# Third-party notices

EZO's own source code does not contain copied code from the projects reviewed in
[`docs/OPEN_SOURCE_AUDIT.md`](docs/OPEN_SOURCE_AUDIT.md):

- APEX-UI
- VoiceStudio
- OpenMontage
- REA
- open-higgsfield

Projects that EZO only studied for ideas are not listed here. Optional external
services such as VoiceStudio and OpenMontage are installed and run separately, under
their own licences, and are not distributed with EZO.

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
| python-docx | 1.2.0 | MIT |
| openpyxl | 3.1.5 | MIT |
| trafilatura | 2.3.1 | Apache-2.0 |
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
