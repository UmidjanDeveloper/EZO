# P1 — isolated OCR and Office conversion in the Student executor (review candidate)

Status: **review candidate, not activated.** Nothing here enables native processing in
the API, changes the production API image, provisions a host or deploys anything.
The trusted-document executor remains separate from any future K4 arbitrary-code
sandbox: it still accepts only a fixed, data-only protocol.

## What changed

| Area | Change |
|---|---|
| Executor image (`documents/executor/Dockerfile`) | Adds Tesseract (`osd`, `eng`, `uzb`, `uzb_cyrl`, `rus`) and LibreOffice Writer/Calc/Impress (`-nogui`) **only** to the executor image, installed at operator build time. The production API image is unchanged and CI still asserts it has neither `tesseract` nor `soffice`. |
| Isolation gate (`documents/isolation.py`) | New `verified_executor_workload()` context. It runs the child's boundary self-check (UID 10001, zero capabilities, no-new-privs, cgroup memory/swap/PIDs/CPU, loopback-only network, read-only root) **inside** the context manager, so no caller can skip it. Outside a verified container it raises. `require_isolation()` / binary discovery accept either this context or the existing test-fixture context; nothing else. |
| Protocol (`documents/executor/protocol.py`) | Requests are a closed, discriminated union: `extract` (pdf/docx/epub/png/jpeg + optional `ocr_languages` from a fixed allow-list) and `convert_pdf` (docx/xlsx/pptx). Unknown fields, operations, formats or languages are rejected. Results add an `OcrSummary` (status, engine, languages, pages, engine-confidence) and a `ConversionResult` (PDF bytes + SHA-256 + page count). |
| Child (`documents/executor/child.py`) | OCR runs only when a PDF has no text layer (or for images), page by page with page numbers, under a soft budget (19 s) inside the unchanged 25 s root watchdog. Scans over `MAX_OCR_PAGES` (6) are **refused** (`page_limit`), never truncated. Conversion runs the OOXML expansion preflight and the existing external-link refusal before LibreOffice opens the file; output size/page caps apply. |
| Controller | Extraction and conversion share one path: atomic one-slot admission, `docker create` limits/verification, bounded pipes, cancellation and forced cleanup are unchanged. Conversion results are re-verified (source hash, PDF hash, `%PDF-` signature). |
| Student ingestion/worker | Accepts PNG/JPEG in addition to PDF/DOCX/EPUB (fixed signatures). The OCR language choice is stored with the immutable source revision; a retry copies it or replaces it explicitly (`?ocr=`). Outcomes: `ocr_required` (no text layer, OCR not requested) and `ocr_incomplete` (page limit/deadline/unavailable/no text) as fixed failure categories. OCR provenance (engine, languages, engine-confidence, low-confidence pages) is stored on the output revision; chunks are marked `ocr: true`. |
| Migration `0022` | Widens the `student_raw_revisions.format` check to include `png` and `jpeg`. Additive; downgrade fails rather than deleting image sources. |
| API | `POST /api/student/uploads?ocr=…&no_ocr=…`, `POST /api/student/readings/{id}/retry?ocr=…`. Default OCR languages: all four. |

## Evidence

Local (this container, no Docker cgroup v2, Debian mirror blocked by the network policy):

- `uv run pytest` (SQLite): all passing; new unit/integration tests cover the protocol,
  fail-closed context, controller result verification, Student OCR choices, retry,
  failure categories, provenance and legacy sources.
- Real LibreOffice on the host converted DOCX, XLSX and PPTX to PDF through
  `child.convert` (page counts and text checked); a DOCX with an external image link
  was refused.
- PostgreSQL 16 (local, no pgvector): Student, document-job, OCR and migration
  upgrade/downgrade tests pass; the one pgvector-specific test needs CI's service.

Real container evidence comes from CI's Docker job
(`scripts/test_isolated_executor.py`): scanned-PDF OCR in each language and with all
four, multi-page page numbers, PNG OCR, refusal above the page limit, Office→PDF for
DOCX/XLSX/PPTX, external-link refusal, the image's language packs, and Student
end-to-end OCR → index → cited answer (mock model) plus "no OCR → retry with OCR".
Measured OCR/conversion seconds are recorded as JUnit properties. **Read the CI run
for results; this document does not claim them in advance.**

## Open gates (unchanged or new)

- Independent review of this change, the image contents and the enlarged native
  attack surface (Tesseract, Leptonica, LibreOffice parse untrusted input inside the
  workload). Dependency/CVE review of the new packages is required before activation.
- `MAX_OCR_PAGES = 6` / `OCR_DPI = 200` are conservative values for one CPU and the
  25 s watchdog; adjust only from measured executor-image evidence. Longer scans
  need batching across separate workloads (not implemented), never a longer deadline.
- PDFs that mix text and scanned pages are read from the text layer only; per-page
  OCR of mixed documents is not implemented.
- OCR confidence is Tesseract's engine score, not calibrated accuracy; handwriting
  is not supported.
- Conversion is available on the controller (`IsolatedExecutor.convert_to_pdf`) but
  is not yet wired to an API job; chat/office tools stay denied in production.
- PID limit 64 and 768 MiB memory also bound LibreOffice; if real documents need
  more, that is a reviewed resource decision, not a silent change.
- Dedicated executor host/VM, deployment topology and activation remain owner
  decisions (see `PER_DOCUMENT_EXECUTOR_REVIEW.md`, `EXECUTION_GATES.md`).
