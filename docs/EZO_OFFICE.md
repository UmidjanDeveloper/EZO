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

Not yet: lossy image recompression, page-level crop, form filling, redaction,
signing. Comparison of two PDFs is implemented in the engine (`compare_pdfs`) and
will be connected to chat in a later step.
