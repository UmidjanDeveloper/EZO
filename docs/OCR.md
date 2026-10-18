# OCR in EZO

EZO reads text from scans and photos **locally** with the open-source
[Tesseract](https://github.com/tesseract-ocr/tesseract) engine (Apache-2.0). No API key,
no upload to a third party, no cost per page.

## Languages

| Pack | Language | Notes |
| --- | --- | --- |
| `uzb` | Uzbek (Latin) | handles `o'`, `g'` and the apostrophe forms used in print |
| `uzb_cyrl` | Uzbek (Cyrillic) | ў, қ, ғ, ҳ |
| `rus` | Russian | |
| `eng` | English | |
| `osd` | orientation and script detection | not a language; used to turn pages upright |

These are Tesseract's own pack names; EZO only uses packs that `tesseract --list-langs`
reports as installed and never invents an identifier. A missing pack is reported
(`/api/status` → `ocr.missing_languages`, and as a warning when a user asks for it).

By default all four packs are used, ordered by the script Tesseract detects on the page
(Latin → `uzb+eng+…`, Cyrillic → `uzb_cyrl+rus+…`), so mixed Latin/Cyrillic pages
still work. A user can name a language in chat ("kirillchada", "ruscha matn",
"inglizcha") to restrict recognition to that pack.

## What happens to a page

1. **Orientation and script** — `tesseract --psm 0 -l osd`. Pages Tesseract is confident
   are sideways or upside down are turned upright (the rotation is recorded).
2. **Preprocessing** (Pillow + NumPy): grayscale, auto-contrast, upscaling of small
   images, deskew of up to ±5° (projection-profile estimate; the angle is recorded).
3. **Recognition** — `tesseract … tsv`: words with boxes and the engine's word confidence,
   grouped into lines and paragraphs.

For PDFs only pages without a text layer are OCR'd (no text, or a few characters on top
of an image), rendered at 300 dpi with pypdfium2. Pages that have text keep it.

## Where it is used

- **Uploads (knowledge base).** Scanned PDFs and images are OCR'd during ingestion; the
  text is chunked and searchable like any other document. Citations of OCR'd chunks say
  "text read by OCR" and keep the page number. Per-page results are stored in the
  `ocr_pages` table (migration 0006) and available at
  `GET /api/knowledge/documents/{id}/ocr`: text, line boxes, page size and dpi,
  language packs, detected script and language, engine version, rotation, deskew angle,
  engine confidence, the hash of the source file and of the page image, warnings, time.
- **Chat.** "Rasmdagi matnni chiqarib ber" / "Распознай текст" / "Extract the text" with
  an attached image or scan → a `.txt` artifact with the recognised text (per page, with
  how each page was read) and the text shown in the reply. The reply model is told to
  show the text as recognised and never to correct, translate or complete it. OCR
  results stored by ingestion are reused when the file has not changed.

## Confidence — what the numbers mean

The confidence EZO shows is **Tesseract's own word confidence (0–100), averaged per
page**. It is useful for spotting bad pages but it is **not** a calibrated probability
of being correct; EZO never presents it as an accuracy percentage. Pages below 60 get a
"check against the original" warning. Pages where nothing was recognised are listed and
left empty: EZO does not guess missing text.

## Measured results (this repository's tests)

Generated test pages (Liberation Sans, 40 px, clean): ≥ 90 % of words read exactly in all
four languages, engine confidence ≈ 95; a page turned 90° and a page skewed 3° were
straightened and read at the same level (`tests/unit/test_ocr.py`,
`tests/integration/test_ocr.py`). These are clean synthetic pages; real phone photos,
stamps, handwriting and low-resolution faxes will score lower. **Handwriting is not
supported** by these Tesseract models.

## Security

- The Tesseract binary comes from server configuration (`EZO_TESSERACT_CMD`, resolved
  with `shutil.which`), never from user input.
- It runs with a fixed argument list, **no shell**, image bytes on stdin, a minimal
  environment (`PATH`, `OMP_THREAD_LIMIT=1`), a per-page timeout
  (`EZO_OCR_TIMEOUT_SECONDS`) and an 8 MB output limit.
- Images pass EZO's image safety gate (format allow-list, size and pixel limits) before
  OCR; PDFs pass the PDF engine's checks (encrypted files are refused).
- At most `EZO_OCR_MAX_PAGES` pages per file; skipped pages are reported, the document
  is marked `partial`.

## Installing

The Docker image installs `tesseract-ocr tesseract-ocr-osd tesseract-ocr-eng
tesseract-ocr-rus tesseract-ocr-uzb tesseract-ocr-uzb-cyrl`. For local development on
Debian/Ubuntu install the same packages; on macOS `brew install tesseract
tesseract-lang`. Check with `tesseract --list-langs`. Without Tesseract EZO works as
before and scans keep the status `needs_ocr` with an explanation.

| Setting | Default | Meaning |
| --- | --- | --- |
| `EZO_OCR_PROVIDER` | `auto` | `auto`/`tesseract` use Tesseract if installed; `none` turns OCR off |
| `EZO_TESSERACT_CMD` | `tesseract` | binary name or path |
| `EZO_OCR_LANGUAGES` | `uzb,uzb_cyrl,rus,eng` | packs to use |
| `EZO_OCR_TIMEOUT_SECONDS` | `60` | per page |
| `EZO_OCR_MAX_PAGES` | `100` | per file |

## Limitations

- Handwriting, very small text (< ~8 px x-height), heavy stamps over text and complex
  multi-column layouts can be read poorly or out of order.
- Tables are read as text lines; table structure is not reconstructed yet.
- OCR → editable DOCX arrives in a later Phase 3 step.
