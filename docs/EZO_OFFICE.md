# EZO Office

EZO Office is the part of EZO that works on the user's own files: PDF page
operations, conversions, OCR, Word/Excel edits and long documents. This page grows
with Phase 3; each section says what is implemented **now** and how it was verified.

## Principles

- **The original upload is never modified.** Every operation creates a new artifact
  (or a new artifact version) and records which inputs it used, with SHA-256 hashes.
- **Deterministic first.** File operations run locally with open-source libraries and
  need no AI model and no API key. A model only writes the reply, and only from the
  facts the operation produced.
- **Verify, don't assume.** Every generated PDF is reopened and its page count checked
  before it is stored; the result is recorded in the artifact's generation metadata.
- **Respect protection.** Password-protected PDFs are refused (EZO never tries to
  guess or bypass a password). PDFs whose permissions forbid changes are refused for
  changes but can still be inspected. Digitally signed PDFs get an explicit warning:
  any change invalidates the signature.

## Using files in chat

Attach files with the paperclip (API: `attachments` — up to 20 of the user's
uploaded document ids, in order). Which files a request is about:

1. the files attached to this message, in the user's order;
2. for a follow-up without attachments ("endi oxirgi betni o'chir"), EZO's latest PDF
   result in this conversation;
3. otherwise the newest uploads of the right type ("shu 4 ta PDF" → the 4 newest PDFs,
   oldest first).

Attaching someone else's document id returns `404 attachment_not_found`. If no file is
found, EZO says so and changes nothing.

## PDF operations (Step 1 — implemented)

Engine: `apps/api/src/ezo_api/documents/pdf/engine.py` (pypdf for structure,
pypdfium2 for rendering, reportlab for stamps). Tool: `pdf_tool`.

| Operation | Example request | Notes |
| --- | --- | --- |
| merge | "Shu 4 ta PDFni birlashtir" | input order kept |
| delete pages | "2, 3 va 5-betlarni o'chir", "oxirgi betini olib tashla" | refuses to empty the file |
| extract pages | "1-3 betlarni ajratib ol" | order as given |
| move page | "6-betni birinchi betga ko'chir" | |
| split | "har 2 betni alohida qil", "bo'lib ber" | max 50 output files |
| rotate | "2-betni 90 daraja bur", "chapga bur" | multiples of 90° only |
| normalize orientation | "yo'nalishini to'g'irla" | turns landscape pages upright; page sizes unchanged |
| page numbers | "sahifa raqamlarini qo'y" | real text; template `{n}` / `{total}` |
| watermark | `suv belgisi "MAXFIY"` | real text, diagonal, semi-transparent |
| header / footer | `pastki qismiga "Hisobot 2026" yoz` | real text |
| compress | "hajmini kamaytir" | **lossless only** (stream compression, duplicate-object removal); if it does not get smaller the original bytes are kept with a warning |
| clean metadata | "metama'lumotlarini tozala" | only on explicit request |
| PDF → images | "rasmga aylantir" | PNG, ≤ 50 pages, zip + previews |
| images → PDF | attach images + "PDF qil" | one image per page |
| inspect | "nechta betdan iborat?" | pages, text layer / scanned pages, encryption, signature, forms, metadata |

Requests are understood in Uzbek (Latin), Russian and English by a rule-based parser
(`documents/pdf/requests.py`); several steps in one sentence run in the order said.
**Page numbers always refer to the input as the user sees it** (after a merge: the
merged document), so "4-betni o'chir, 6-betni birinchi betga ko'chir" moves the
original page 6. Only when files are attached, nothing was recognised and a model is
available, a planner model may propose the same structured steps (validated by the
same schema); it never executes anything itself.

Each result artifact carries: the steps, input provenance (id, title, version,
sha256, size, MIME), the report lines, warnings, engine, duration, the output hash and
size, and `verification: {reopened, page_count, expected_pages}`. Previews of the
first 6 pages are PNG exports.

Limits: 200 MB per input and in total, 3,000 pages, 20 inputs, 12 steps, 180 s.

Verified by `tests/unit/test_pdf_engine.py` (real PDFs generated in the test),
`tests/unit/test_pdf_requests.py` (every example above) and
`tests/integration/test_pdf_office.py` (chat end to end, including offline with no
providers configured).

Not yet (PDF): lossy image recompression, page-level crop, form filling, redaction,
signing. Comparison of two PDFs is implemented in the engine (`compare_pdfs`) and
will be connected to chat in a later step.

## OCR (Step 2 — implemented)

Scans and photos are read locally with Tesseract (Uzbek Latin and Cyrillic, Russian,
English) during upload and on request in chat. Details, measured results and limits:
[OCR.md](OCR.md).

## Word files (Step 3 — implemented)

Translation, proofreading, formal style and rewriting of a `.docx` edit **the original
file in place**: styles, fonts, inline bold/italic/colour, hyperlinks, numbering, tables,
images, headers/footers and page setup are kept and checked after saving. On request
the edits are real Word tracked changes. `«X» ni «Y» ga almashtir` is a find-and-replace
that needs no model. The whole document is processed in batches; nothing is silently
cut off. Details and measured results: [DOCUMENT_FIDELITY.md](DOCUMENT_FIDELITY.md).

## Conversions, tables and spreadsheets (Step 4 — implemented)

All of these run locally without an AI model or API key
(`tests/integration/test_convert_office.py` runs them with no provider configured).

### Scan or photo → Word / searchable PDF

| Request | Result |
| --- | --- |
| "Shu skanni Word ga aylantir" | **editable** `.docx`: paragraphs and headings in reading order; hyphenated line ends re-joined |
| "…asl ko'rinishini saqlab Word ga o'tkaz" / "layout" / "как в оригинале" | **layout** `.docx`: one paragraph per recognised line, with its indentation, vertical spacing, approximate font size and a page the size of the original (one section per page) |
| "Bu PDFni qidiriladigan PDF qil" / "searchable PDF" | **searchable PDF**: the page images as they were, plus an invisible text layer written by Tesseract; pages that already had text are copied unchanged |

Pages where nothing could be read become a visible placeholder
("[page 2: no text could be read]"); nothing is filled in. Mixed PDFs keep the text of
pages that already have a text layer. Layout mode is not a pixel copy: fonts, columns
and pictures are not rebuilt; for the exact look use the searchable PDF.

A PDF that already has text is converted to Word from its text layer (the earlier
conversion). Its page layout, images and fonts are not carried over, and the reply
says so.

### Tables → Excel

"Shu PDFdagi jadvalni Excelga chiqar" / "extract the tables" / "извлеки таблицы в Excel"
→ one `.xlsx` with a sheet per table.

- **Word**: read exactly from the file's table structure (merged cells appear once).
- **PDF with a text layer**: words and positions from PDFium; a table is ≥ 3
  consecutive rows that split into ≥ 2 aligned columns (right-aligned numbers
  included).
- **Scans/photos**: the same detection on OCR word boxes.

Detected tables carry warnings when rows have missing cells. Tables without clear
column gaps, or with merged cells spanning columns, may be split or merged wrongly, so
the reply asks the user to check them.

### Spreadsheet operations

On an attached `.xlsx`/`.csv`, using the sheet's **real column names** found in the
request:

| Request | Operation |
| --- | --- |
| "Aholi bo'yicha kamayish tartibida sarala" / "Отсортируй по … по убыванию" | sort (numbers as numbers, empty cells last) |
| 'Faqat Viloyat "Toshkent" bo'lgan qatorlarni qoldir', "Aholi > 380000" | filter |
| "Dublikatlarni o'chir", "bo'sh qatorlarni olib tashla" | remove duplicates (first kept) / empty rows |
| "Jami qator qo'sh" | total row |
| "Viloyat bo'yicha guruhlab Aholi yig'indisini hisobla", "group by … average …" | group-by with sum / count / mean / min / max |

Every number is computed by EZO and written as a value. The original formatting and
formulas are not carried over, and the reply says so. Formula cells whose result was
never saved (e.g. files written by scripts) are **reported, not calculated**. A
column that does not exist is refused. Macros are never run, and `.xlsm` is not accepted.

## Long documents (Step 5 — implemented)

The old 40,000-character limit is gone. A long file is now processed **completely**:

- **Split at its own structure.** Markdown headings, `1.2.`, `5-modda`, `II bob`, `Статья 5`,
  `Глава 2`, `Article 3`, short ALL-CAPS headings. Over-long sections are split at
  paragraph (or sentence) boundaries into parts of ≤ 12,000 characters. Every part keeps
  its section titles (`documents/longdoc.py`).
- **Summary** (chat or file): each part is summarised, then the summaries are combined
  in rounds if needed (map-reduce). The reply says "EZO read ALL of …" with the
  character and part counts and lists the document's sections.
- **Translation / proofreading / rewriting** of long text files are done part by part
  and joined in order. Word files use the in-place editor from Step 3, which also
  processes the whole file.
- **Questions** about a long file search **the whole file** (keyword + semantic search
  restricted to that document) and answer from the most relevant passages, with their
  pages and sections. If the passages do not contain the answer, EZO says so instead of
  guessing.
- **Resumable.** Each finished part is stored (`long_doc_parts`, migration 0007, keyed
  by the part's content hash and task). If the AI provider fails half-way, the reply
  says how far it got. Asking again continues from that point: done parts are reused,
  not paid for twice.
- **No silent truncation.** Texts over 2,000,000 characters (~800 pages) are refused
  with an explanation. The artifact metadata records `long_document: {chars, parts,
  reused_parts, method}` and `partial: false`.

Requires an AI model (summaries and translations are model work). Offline, EZO says so
and does not pretend.
