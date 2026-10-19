# EZO implementation status

What is **verified** to work, how it was verified, and what is not done. Nothing is listed as
working unless it was tested. The one roadmap is [ROADMAP.md](ROADMAP.md).

## Verification convention

Two kinds of results are reported, **never mixed**:

1. **CI verified** — what GitHub Actions ran on a specific commit (workflow *CI*: jobs *API*,
   *Web* and *Docker*). This is the authoritative number. Every CI job ends with a
   `scripts/test_report.py` table (collected / passed / failed / skipped and every skip
   reason) in the job log and the run summary. Quote that table, with the run number and
   commit.
2. **Extended local verification** — checks CI cannot run, listed by name: Docker builds
   in the development sandbox, live provider calls, manual UI checks. These are reported
   as "local, not in CI". (Since Stage A, CI installs LibreOffice and Tesseract and sets
   `EZO_REQUIRE_OFFICE=1` / `EZO_REQUIRE_TESSERACT=1`, so those tests fail instead of
   skipping when the tools are missing.)

Why the numbers differ between environments (all expected):

| Test | SQLite (CI) | PostgreSQL (CI) | Local |
|---|---|---|---|
| pgvector store test | skipped (needs PostgreSQL + pgvector) | runs | runs on PostgreSQL |
| LibreOffice and Tesseract tests | run (required) | run (required) | skip unless installed, or fail with `EZO_REQUIRE_OFFICE=1` / `EZO_REQUIRE_TESSERACT=1` |

Produce the same table locally:

```bash
cd apps/api
uv run pytest -q -rs --junitxml=reports/sqlite.xml
EZO_TEST_DATABASE_URL=postgresql://ezo:ezo@localhost:5432/ezo_test \
  uv run pytest -q -rs --junitxml=reports/postgres.xml
cd ../.. && python3 scripts/test_report.py \
  "API · SQLite=apps/api/reports/sqlite.xml" "API · PostgreSQL=apps/api/reports/postgres.xml"
```

Test counts are not a quality score: a phase is judged by which failure modes its tests cover
(listed per phase below), not by how many tests exist.

## Current capabilities

Phase numbers follow the 2026-10-18 master prompt (see ROADMAP.md); the history below keeps
the names used when each record was written.

Source of truth: `apps/api/src/ezo_api/maturity.py` and the agent catalog (also returned by
`GET /api/status` as `agents` and `features`). A test keeps them consistent with ROADMAP.md.

| Capability | Phase | Maturity |
|---|---|---|
| EzoCore chat, routing, personality, memory | Foundation | alpha |
| Files, knowledge base, citations; ResearchAgent | Knowledge | alpha |
| Turn-by-turn voice, orb presence states | Voice | alpha |
| Artifacts with versions and exports | Artifacts | alpha |
| Story projects (API only) | Artifacts | experimental |
| DocumentAgent + document formats | Documents | alpha |
| PresentationAgent + slide engine | Presentations | alpha |
| Native missions (in memory, not in chat) | Orchestration foundation | experimental |
| LanguageCoachAgent, IELTS-style simulator, progress | Phase 1 | alpha |
| VisualAgent: images, edits, diagrams, social graphics, logos, slide images | Phase 2 | alpha |
| OCR + EZO Office (PDF tools, OCR, DOCX fidelity, tables, sheets, long documents, Word/Excel → PDF) | Phase 3 | alpha (partially complete) |
| Professional writing (30 document types, official layout, organization profile, validation) | Professional writing | alpha |
| Translation (uz Latin/Cyrillic, ru, en; Word in place; glossary; quality checks; bilingual files; turn-based interpretation API) | Translation | alpha |
| Education materials (lesson packages, quizzes, syllabi, rubrics, study plans) | Phase 4 | alpha |
| Academic research (OpenAlex, research plans, 6 citation styles) and career (profile, CV, letters, interviews) | Phase 4 | alpha |
| Durable tasks / jobs / worker | Phase 5 | planned |
| Persistent missions in chat | Phase 6 | planned |
| LegalResearchAgent + official-source framework (LEX.UZ proof of concept, off by default, live access unverified) | Phase 7 | experimental |
| Realtime voice | Phase 8 | planned |
| DeveloperAgent + website builder | Phase 9 | planned |
| DataAnalystAgent | Phase 10 | planned |
| BrowserAgent | Phase 11 | planned |
| Video / motion | Phase 12 | planned |
| BusinessAgent | Phase 13 | planned |
| Ruflo provider | Phase 14 | planned (off by default) |

Planned agents are never shown as working: the GeneralAgent answers and states the
limitation.

## Latest verified baseline

**CI verified** — run #56 (CI), commit `f6f7743`, all jobs green
(https://github.com/UmidjanDeveloper/EZO/actions/runs/39192571554):

| Suite | Collected | Passed | Failed | Skipped | Skip reasons |
|---|---:|---:|---:|---:|---|
| API · SQLite | 665 | 664 | 0 | 1 | needs PostgreSQL + pgvector |
| API · PostgreSQL | 665 | 665 | 0 | 0 | — |
| Web unit (Vitest) | 44 | 44 | 0 | 0 | — |
| Shared unit (Vitest) | 10 | 10 | 0 | 0 | — |
| Playwright e2e | 28 | 28 | 0 | 0 | — |

Also green in that run: ruff, format check, mypy, `alembic check` on PostgreSQL (migrations
up to 0011), ESLint, TypeScript, the web production build, and the Docker job. The
Docker job covers the Compose config, the API and web image builds, Tesseract with `uzb`,
`uzb_cyrl`, `rus`, `eng` and `osd` in the API image, **the API image converting a Word
and an Excel file to PDF with LibreOffice**, the API container migrating and answering
`/api/health`, and the web container serving `/`. CI installs Tesseract and LibreOffice
and sets `EZO_REQUIRE_TESSERACT=1` and `EZO_REQUIRE_OFFICE=1`, so the OCR and LibreOffice
tests **run** (no LibreOffice skips any more).

**Extended local verification** (not in CI):

- Same code, with LibreOffice and Tesseract 5.3.4 and `EZO_REQUIRE_*` set: SQLite 664
  passed + 1 skipped (pgvector); PostgreSQL 665 passed.
- Migration 0011 verified up → check → down → up on SQLite and PostgreSQL.
- The full Playwright suite passed locally (28).
- A letter in an approved template and a document on EZO's letterhead were converted to
  PDF with LibreOffice and inspected visually (letterhead, header with QORALAMA, logo,
  placeholders for signature and number).
- OpenAlex live access **not verified**: the sandbox network blocks it; the client is
  tested with a mock transport and the chat flows with a fake search.
- The API Docker image could **not** be rebuilt in the sandbox (the sandbox proxy blocks
  deb.debian.org). The CI Docker job built and checked it.
- Live provider tests **not performed** (no provider keys here): the quality of AI-written
  drafts, translations, teaching materials and research plans has only been checked with
  scripted model replies.

## Stage E1 — Organization profiles (2026-10-19) — alpha

Commits `7182eda` (backend, migration 0011), `a98eefd` (Settings UI, e2e), `f6f7743`
(docs). CI runs #54–#56 green. Details: [docs/GOVERNMENT_WORK.md](docs/GOVERNMENT_WORK.md).
E2–E4 (secretary, citizen appeals, reports) are **not built**.

### What works

- **Profile** (`organization/`, migration 0011): standard formatting (font, size, line
  spacing, indent, A4 margins), logo (re-encoded to PNG), terminology, approved Word
  templates (`{{matn}}` marker; header, footer, styles and margins kept; macros and
  external links refused), example documents (style references only), ZIP export,
  deletion with stored files. Every change audited.
- **Use**: official letters/acts/minutes are written into the approved template for the
  document type (else a general one), otherwise on EZO's letterhead with logo and
  formatting; other documents get the letterhead on request ("tashkilotimiz
  blankasida"); presentations that mention the organization use its name (cover author),
  style and terms. Examples are sent only inside `<example>` tags; their numbers are not
  evidence and are flagged.
- **Fix**: "blankasida" / "на бланке" no longer means "empty template".
- **Settings UI**: formatting, terminology, logo with preview, templates per document
  type, examples, export, delete with confirmation.

### Acceptance scenarios (tests)

| Scenario | Test |
|---|---|
| Logo upload (PNG out, SVG refused), template with marker and type, example excerpt, wrong type refused, download headers, ZIP export contents, foreign profile 404, profile deletion removes stored files | `tests/integration/test_organization.py::test_profile_files_export_and_deletion` |
| "Tashkilotimiz blankasida … xizmat xati": template letterhead and header kept, sample text removed, examples sent as `<example>`, number from the example flagged | `::test_letter_uses_the_approved_template_and_examples_only_as_style` |
| Uzbek Cyrillic request on the letterhead | `::test_cyrillic_letter_on_the_letterhead` |
| Other document with letterhead and logo; presentation author = organization, preferred terms in the planner prompt | `::test_other_documents_and_presentations_use_the_profile` |
| Formatting, template marker, margins, logo, file checks, external-link template refused | `tests/unit/test_organization.py` |
| "blankasida" is not a template request | `tests/unit/test_writing.py` |
| Settings: formatting, terms, logo, DOCX template, example, reload, export, letter in chat, delete | e2e `organization.spec.ts` |

### Not done

One default profile only (no switching by name); `.docx` templates only; EZO writes only
into the main body at the marker; the logo is not placed into approved templates (they keep
their own); PDF/Markdown/text versions carry the letterhead as text; no import from an
export ZIP. Quality with a live model was not measured.

## Stage D — Education, academic research and career (2026-10-19) — alpha

Commits `67bb6a1` (education materials), `0420e86` (academic), `e7f6aa6` (career),
`739ae1d` (web: career profile, e2e), `7317af8` (docs). CI runs #48–#52 green. Details:
[docs/EDUCATION_CAREER.md](docs/EDUCATION_CAREER.md).

### What works

- **Teaching and study materials** (`education/`, `agents/education_office.py`): lesson
  package (Word + PDF, Excel with quiz/timing/rubric, slides through the presentation
  engine), quiz with an EZO-built answer key, syllabus, rubric, study plan, thesis-defense
  and job-interview questions. Options from the request (questions, minutes / "para",
  weeks, level, slides, language, Cyrillic). Attached files are the source material.
  EZO checks answers, question counts, lesson timing, syllabus weights and week numbers,
  rubric points and weekly minutes. Templates without a model.
- **Academic** (`academic/`, `agents/academic_office.py`): OpenAlex literature search
  (no key) through `SafeFetcher.fetch_json`; a research plan that may cite only the found
  works as [n] (non-existent citations removed, stated "results" flagged); reference
  lists written by EZO in APA 7, MLA 9, Chicago, Harvard, IEEE and GOST; an Excel
  literature matrix; a literature list without a model; pasted reference lists split by
  the model and every value verified against the user's text. `/api/academic`.
- **Career** (`career/profile.py`, migration 0010): career profile in Settings; a CV
  built exactly from it with no model; cover and motivation letters with the profile as
  their only facts (other numbers flagged); interview questions from the profile.
  `/api/career/profile`.

### Acceptance scenarios (tests)

| Scenario | Test |
|---|---|
| Lesson request → Word + Excel + 3-slide PPTX, 45 minutes checked, key "A" | `tests/integration/test_education.py::test_lesson_package_makes_word_excel_and_slides` |
| Quiz from an attached lecture: file text sent, broken answer and short count reported | `::test_quiz_from_an_attached_lecture_reports_problems` |
| No AI key: Cyrillic study-plan template; lesson template totals 45 minutes | `::test_template_without_a_model_and_cyrillic`, e2e `education.spec.ts` |
| Research plan: only found works cited, [7] removed, "Natijalar shuni ko'rsatdiki" flagged, APA list by EZO, missing fields listed | `tests/integration/test_academic.py::test_research_plan_cites_only_found_works` |
| Literature list without a model (IEEE); search off → nothing invented, 503 | `::test_literature_list_without_a_model_and_search_off` |
| Pasted references: an invented DOI dropped | `::test_reference_formatting_drops_invented_fields`, `tests/unit/test_academic.py` |
| Six citation styles, OpenAlex parsing and request URL | `tests/unit/test_academic.py` |
| CV from the profile with no model call; profile replace/delete | `tests/integration/test_career.py::test_profile_api_and_cv_without_a_model`, e2e |
| Letter: profile number kept, invented 45 % flagged; interview answers from the profile | `::test_letters_and_interview_use_only_profile_facts` |

### Not done

No grade book or online tests; quizzes are files. The CV keeps the profile's entries in
the language they were written. OpenAlex coverage of Uzbek-language journals is limited
and live access was not verified here. Content quality with a live model was not
measured.

## Stage C — Translation (2026-10-18) — alpha

Commits `2830ab5` (service, Latin/Cyrillic, glossary, checks, chat, API), `1d5635a`
(Translation page), `29577b9` (docs). CI runs #44, #45, #46 green. Details:
[docs/TRANSLATION.md](docs/TRANSLATION.md).

### What works

- **Text translation** between uz (Latin), uz (Cyrillic), ru and en, in chat ("Inglizchaga
  tarjima qil: …") and at `/api/translation/translate` and on the Tarjima page. Source
  and target are read from the request ("ruschadan o'zbek lotiniga", "с русского на
  узбекский", "kirillga"); styles: general, official, academic, business, technical,
  legal. Long texts go in paragraph batches; the model lists ambiguous places.
- **Uzbek Latin ↔ Cyrillic without a model** (`translation/translit.py`): text, and Word
  files converted in place run by run (formatting, tables, headers kept). Into Uzbek
  Cyrillic from another language, the model writes Uzbek and EZO converts the script.
- **Documents** reuse the existing pipeline: Word in place (DOCX fidelity with a review
  hook), other files through Markdown, long files part by part. "ikki tilli" adds a
  two-column bilingual Word file.
- **Terminology memory**: glossary per user, optionally per organization (migration
  0009), editable on the page or in chat ("Glossariyga qo'sh (inglizcha): «X» → «Y»").
  Matching tolerates word endings and either script; only matching terms go to the model.
- **Checks** (`translation/quality.py`, no model): numbers (separators, month names),
  links, surnames in any script, glossary use, empty / untranslated / length-changed
  paragraphs, script, ambiguities. Shown in chat, the page and the artifact metadata.
- **Turn-based voice interpretation** at `/api/translation/interpret` (speech → text →
  translation → speech; in a conversation, whichever side speaks is translated to the
  other). Simultaneous interpretation is only an interface.

### Acceptance scenarios (tests)

| Scenario | Test |
|---|---|
| "Shu ruscha hujjatni o'zbek kirilliga tarjima qil, ikki tilli…" → Word file in Cyrillic, heading style and bold kept, glossary term used, bilingual export | `tests/integration/test_translation.py::test_russian_word_file_into_uzbek_cyrillic_with_bilingual_export` |
| Text in the message with a glossary term → term sent to the model, checks pass | `::test_text_in_the_message_with_glossary_and_checks` |
| Changed number, invented number, changed name, ambiguity → all reported | `::test_problems_are_reported_not_hidden`, `tests/unit/test_translation.py::test_quality_report` |
| No AI key: Latin ↔ Cyrillic of text and a Word file works; translation says it needs a provider | `::test_script_conversion_works_without_a_model`, e2e `translation.spec.ts` |
| Glossary: API, chat command, unclear languages refused, another user's terms invisible, organization deletion removes its terms | `::test_glossary_api_chat_and_privacy` |
| Interpretation turn: transcript, translation, speech | `::test_turn_based_interpretation` |
| Latin ↔ Cyrillic rule cases (o'/g', ye/yo, e/э, ц, ъ, months, links, all caps, split runs) | `tests/unit/test_translation.py` |

### Not done

PDF page layout is not kept (PDF and scans are translated as text into Word); no UI for
voice interpretation; no glossary import/export; the ц/soft-sign vocabulary for Latin →
Cyrillic is short; translation quality with a live provider was not measured; Russian
text written in Cyrillic would be letter-converted by "lotinga o'gir" (use translation).

## Stage B — Professional writing (2026-10-18) — alpha

Commits `535d16c` (service, layouts, organization profile API, chat), `ccac79e` (Settings
card), `26eb571` (docs). CI run #42 green. Details: [docs/PROFESSIONAL_WRITING.md](docs/PROFESSIONAL_WRITING.md).

### What works

- **30 document types** (`writing/catalog.py`): ariza, tushuntirish xati, bildirishnoma,
  xizmat xati, rasmiy murojaat, javob xati, ma'lumotnoma, tavsiyanoma, taqdimnoma,
  dalolatnoma, bayonnoma, yig'ilish protokoli, buyruq and qaror (drafts), hisobot, ish
  rejasi, xulosa, taklif xati, taklifnoma, tabriknoma, ma'ruza, nutq, press-reliz, e'lon,
  tadbir dasturi, ishonchnoma (draft), CV, motivatsion xat, cover letter, research
  proposal. Each has its fields, section order, layout and default length. Recognised from uz/ru/en
  requests ("Hokimlikka xizmat xati tayyorla", "CV yoz", "Bayonnoma shablonini ber").
- **Options from the request**: writing mode (official, academic, natural, business,
  journalistic, persuasive, concise, speech…), length, language and script (Latin/Cyrillic, ru, en), audience, "without the
  draft label".
- **Drafting**: the model writes only content, as JSON in the type's structure. EZO then
  validates it: fields carrying a number or date the user never gave are emptied back to
  a placeholder; such numbers in the body are listed for checking; claims of signing,
  approval or a seal are flagged; Uzbek style lint (clichés, inflated phrasing, mixed
  scripts, repetition, very long sentences); length and script checks.
- **Official layout DOCX** (`writing/render.py`): A4, 30/15/20/20 mm, Times New Roman 14,
  letterhead with a rule, № and date line, recipient block, centred title, signature table
  and [M.O.] with placeholders only, "QORALAMA" in the page header of official drafts.
  Exports: PDF (LibreOffice layout, else EZO's text PDF, labelled), Markdown, plain text.
- **Templates without a model**: "… shablonini ber", or any writing request when no AI
  provider is configured, gives the same layout with placeholders (no cost).
- **Organization profile** (migration 0008, `/api/writing/organizations`, Settings →
  Organization): name, department, contacts, head, letterhead, house style, preferred
  terms. Used for the letterhead and given to the model as user-entered facts.

### Acceptance scenarios (tests)

| Scenario | Test |
|---|---|
| Explanatory note from the user's facts → title, recipient, signature placeholder; a date the user never gave becomes "[Sana]" | `test_writing.py::test_explanatory_note_from_facts` |
| Invented number in the body and "imzolandi" → both reported to the user | `test_writing.py::test_invented_numbers_and_claims_are_reported`, `tests/unit/test_writing.py` |
| Organization profile → letterhead, preferred terms sent to the model; edit and delete | `test_writing.py::test_organization_profile_letterhead_and_terms` |
| Template request → no drafting call | `test_writing.py::test_template_request_uses_no_model` |
| No AI provider → labelled template with PDF/MD/TXT exports | `test_writing.py::test_offline_gets_a_labelled_template`, `test_document_agent.py`, `test_convert_office.py` |
| Russian request → Russian draft | `test_writing.py::test_document_types_endpoint_and_russian` |
| Another user's profiles are invisible (list, edit, delete → 404); only one default | `test_writing.py::test_organization_profiles_are_private_and_one_is_default` |
| Settings → Organization profile saves and reloads | e2e `writing.spec.ts` |

### Not done

Logo/seal images and example documents in the profile; verifying names, positions or
legal grounds against official sources (Stage F); revising an existing draft section by
section in chat (a follow-up request re-drafts); Telegram/press work (Stage G). Prose
quality depends on the model and was not measured with a live provider.

## Stage A — Office completion (2026-10-18)

Commits `824dbcf` (LibreOffice conversion), `f9694f0` (CI: Impress for the required
presentation test). Run #39 failed (the presentation-opening test now runs and needed
Impress); run #41 green.

- **Word / Excel → PDF with LibreOffice** (`documents/office_convert.py`, tool
  `office_pdf`): fixed argv, no shell, fresh profile and temp dir per call, process-group
  kill on timeout, one conversion at a time, input/output size and page limits. Files
  with external links (linked images, OLE, external data) are refused. Every PDF is
  reopened and its pages counted. Without LibreOffice, chat says so and labels the
  text-based fallback.
- "Word faylni PDF ga aylantir", "Excel faylni PDF qilib ber", "PDFni Wordga aylantir":
  the target format is the one with a target marker (-ga, qilib, to, into, в…).
- The API Docker image installs `libreoffice-writer-nogui`, `libreoffice-calc-nogui` and
  fonts (Liberation, DejaVu); CI checks the conversion inside the image.
- Regression fixtures: a two-page official letter (letterhead, PAGE footer, Latin +
  Cyrillic, table, page break), a landscape page, a two-sheet workbook with a formula, a
  file with an external image link.

## Sprint 0 — Stabilization (2026-10-17)

**What changed**
- One authoritative ROADMAP (Done / Next in the agreed order); the old milestone structure
  is removed everywhere (docs, code comments, one user-visible OCR message).
- The agent catalog has a roadmap `phase` and a `maturity` label instead of milestone
  numbers. Availability is derived from maturity, so a planned agent can never run. A new
  `maturity.py` covers non-agent capabilities; both are exposed in `/api/status` (`agents`,
  `features`).
- Verification convention: `scripts/test_report.py` reads JUnit reports from pytest,
  Vitest and Playwright, and prints the same table in CI (job log and run summary) and
  locally (`python scripts/ezo.py test`).
- CI Docker job: Compose validation, API and web image builds, API and web smoke tests.
  Optional services (VoiceStudio) are not built.
- Security: `security.yml` (pip-audit, pnpm audit; weekly and on dependency changes),
  Dependabot (opens PRs only, minor and patch, no majors), `docs/SECURITY.md`.
- Owner documents: `docs/GIT_WORKFLOW.md` (no `main` or branch protection exists yet; exact
  steps given) and `docs/OWNER_DECISIONS.md` (EZO has no LICENSE — not chosen on the owner's
  behalf).

**Files added:** `apps/api/src/ezo_api/maturity.py`, `apps/api/tests/unit/test_catalog.py`,
`scripts/test_report.py`, `.github/workflows/security.yml`, `.github/dependabot.yml`,
`docs/SECURITY.md`, `docs/GIT_WORKFLOW.md`, `docs/OWNER_DECISIONS.md`.
**Files modified:** agent catalog, status schema and route, shared types, CI workflow,
Playwright config, `scripts/ezo.py`, `.gitignore`, ROADMAP, IMPLEMENTATION_STATUS, README,
ARCHITECTURE, TROUBLESHOOTING, `.env.example`, a few code comments.
**Database migrations:** none.

**Tests added:** catalog consistency (exactly the implemented agents are available, planned
agents have limitation notes, every phase exists in ROADMAP, unique feature keys).

**Security changes:** dependency audits and update policy, documented security model.

**User-visible changes:** none in the UI. `/api/status` returns `maturity`, `phase` and
`features`; the "needs OCR" message no longer names an obsolete milestone.

**Known limitations / not done:** branch protection and `main` need the owner. The CI
actions still run on Node 20 (GitHub forces them to Node 24 and shows a warning; no
failure). Dependabot has started scanning and may open PRs on this branch, since it is the
repository's default branch.

**How the owner can test:** open the Actions tab → latest *CI* run → each job's summary
shows the test table. `curl localhost:8000/api/status` lists agents with
`maturity`/`phase`.

## Phase 3 — OCR + EZO Office (2026-10-18) — alpha, partially complete

Commits `73bdd41` (PDF engine), `d795ba8` (OCR), `6169895` (Word in place), `0072bb2`
(conversions, tables, sheets), `fdaeb28` (long documents), `f419560` (chat UX), `aa9d894`
(official-knowledge plan), `0ea8d6e` (regression pass). Every commit's CI run was green (runs #30, #31 and #33–#37).

### What works

- **PDF engine, offline** (`documents/pdf/`): merge, delete / extract / move / rotate pages,
  split, orientation, page numbers, watermark, header/footer, lossless compression,
  metadata cleaning, images ↔ PDF, inspect, page-level compare. Requests are understood
  in uz/ru/en; several steps in one sentence keep page identity. Every output is reopened
  and its page count verified. Encrypted PDFs are refused, restricted ones are read-only,
  signed ones get a warning.
- **OCR, local Tesseract** (`documents/ocr/`): `uzb`, `uzb_cyrl`, `rus`, `eng`, with
  orientation detection, deskew, line boxes and engine confidence (labelled as an engine
  score). OCR runs during ingestion (pages without a text layer), and its chunks are
  cited as "text read by OCR". In chat it produces a `.txt` file. Scans can also become
  editable or layout Word, or a searchable PDF. Per-page results are stored (migration
  0006) and exposed at `/api/knowledge/documents/{id}/ocr`.
- **Word in place** (`documents/docx/fidelity.py`): translate / proofread / formal /
  rewrite keep runs, styles, numbering, tables, images, headers/footers and hyperlinks.
  A before/after inventory is stored. Real tracked changes are available on request, and
  find-and-replace needs no model.
- **Tables → Excel**: Word tables are exact; tables in PDFs (PDFium word boxes) and scans
  (OCR word boxes) are detected. **Spreadsheet operations**: sort, filter, duplicates,
  empty rows, totals, group-by, all computed by EZO. Formula cells without a saved result
  are reported, not calculated.
- **Long documents**: section-aware parts, map-reduce summaries, part-by-part
  translations, whole-file search for questions. Parts are cached (migration 0007), so a
  job continues after a provider failure. The 40,000-character limit is gone.
- **Chat**: files are attached to the message (ordered, ownership-checked, up to 20).
  Chips show on the user message, PDF results show a first-page preview, and a send waits
  while uploads are in flight.

### Acceptance scenarios (tests)

| Scenario | Test |
|---|---|
| A — 3 attached PDFs: "Birlashtir va 2-betni olib tashla" → right pages, order, download | `test_pdf_office.py::test_scenario_a_merge_three_attached_pdfs_and_delete_page_two` (+ e2e `pdf-office.spec.ts`) |
| B — Scanned Uzbek document (Latin/Cyrillic, rotated/skewed) → text, Word, searchable PDF | `test_ocr.py`, `test_convert_office.py::test_scan_to_editable_and_layout_word`, `::test_searchable_pdf_keeps_text_pages` |
| C — Word file translated with its formatting kept; tracked changes on request | `test_docx_office.py`, `tests/unit/test_docx_fidelity.py` (incl. LibreOffice opening the result) |
| D — Long document: whole file summarised, job resumes after a failure, questions search everything | `test_long_documents.py` |
| E — No API key: PDF operations, OCR, conversions, tables, sheets, find-and-replace still work | `test_pdf_office.py::test_scenario_e_…`, `test_convert_office.py` (no providers), `test_docx_office.py::test_find_and_replace_needs_no_model` |

### Measured results

- OCR on clean generated pages (40 px Liberation Sans): ≥ 90 % of words exact in all four
  languages, engine confidence about 95. A page rotated 90° and one skewed 3° are
  straightened. Real photos, stamps and handwriting will be worse. Handwriting is not
  supported.
- Word fidelity on the rich fixture (heading, bold amount mid-sentence, hyperlink, red
  italic text, numbered list, table, image, header, footer with a PAGE field): every
  inventory property unchanged after translation. The bold, italic and colour stayed on
  the translated words, and LibreOffice opens the result.

### Not done (why Phase 3 is "partially complete")

(XLSX → PDF and LibreOffice in the Docker image were added in Stage A.) Editing Word
footnotes/endnotes/comments/charts; handwriting OCR; an LLM planner for sheet
operations; a multi-page document viewer in the UI. Pathological PDFs cannot be killed
mid-parse (thread), only abandoned. A separate worker process is planned with Phase 5.

## Official knowledge sources + OpenCode evaluation (2026-10-18) — experimental

**What changed**
- `OfficialSourceConnector` framework (`official/`): each source has an `AccessReview` (official
  API, robots.txt, terms, formats, rate limits, legal basis); unverified sources cannot be
  enabled. `OfficialHttpClient` allows only the source's hosts, obeys robots.txt (fail closed),
  paces requests (≥ 5 s, Crawl-delay), caps requests per run, never works around 401/403/451
  and honours 429 Retry-After.
- LEX.UZ proof-of-concept connector (public `/docs/<id>` and `/ru/docs/<id>` pages), **off by
  default**. Metadata comes from the page title; the status only from an explicit label.
  gov.uz, president.uz, E-qaror and ministry sites are registered as unverified (no invented
  endpoints).
- Resumable, rate-limited sync into the existing knowledge base. Each document is new,
  unchanged, amended (new revision, history kept) or a duplicate. Outdated acts are filtered
  out, interrupted runs are recovered at startup and can be resumed, and live verification
  keeps the last verified time when it fails.
- LegalResearchAgent (experimental): `official_search` (both Uzbek scripts) and
  `verify_official_document` tools. Answers carry number, date, status, article, retrieval
  date and official URL; EZO never claims "in force" when the status is unconfirmed or a live
  check failed; it compares the last two retrieved revisions on request.
- `/api/official`: sources with access reviews, sync, runs, resume, documents with revisions
  and provenance, live verify (audited, rate-limited).
- `docs/OPENCODE_INTEGRATION_PLAN.md`: OpenCode (MIT) recommended only as an optional,
  sandboxed coding backend behind a future DeveloperAgent; not installed.

**Files added:** `apps/api/src/ezo_api/official/{base,http,legal_text,lexuz,registry,sync}.py`,
`apps/api/src/ezo_api/db/models/official.py`, `migrations/versions/0005_official_knowledge_sources.py`,
`apps/api/src/ezo_api/tools/official_tools.py`, `apps/api/src/ezo_api/agents/legal_research.py`,
`apps/api/src/ezo_api/api/routes/official.py`, `tests/official_fixtures.py`,
`tests/unit/test_official_sources.py`, `tests/integration/test_official_sync.py`,
`tests/integration/test_legal_research.py`, `docs/OFFICIAL_SOURCES.md`,
`docs/OPENCODE_INTEGRATION_PLAN.md`.
**Files modified:** `knowledge/fetch.py` (HTTP status and Retry-After on errors),
`KnowledgeService.add_connector_document`, settings (`EZO_OFFICIAL_*`), services, startup
recovery, agent registry and catalog (legal_research experimental), `maturity.py`, intent rules
(Uzbek Cyrillic legal words), two existing tests, docs, `.env.example`.
**Database migrations:** `0005_official_knowledge_sources` — `legal_documents`,
`legal_revisions`, `official_sync_runs`. Verified up → `alembic check` → down → up on SQLite
and PostgreSQL.

**Tests added:** 19 unit cases (title parsing in 4 forms, document types, impossible dates,
status only from labels, transliteration, articles, LEX.UZ ID/URL validation, parsing in Uzbek
Latin/Cyrillic and Russian, robots.txt obey/fail-closed, refusals, rate limits, host
allow-list, budget, network errors, registry), 12 sync integration tests (metadata + indexing
+ raw provenance, unchanged/amended with history, duplicates, outdated filtering,
Cyrillic/Russian, interrupted-run recovery and resume, repeated network failures, access
refusal, robots disallow, Retry-After within/over the cap, pacing, unsupported/disabled sources,
live verification incl. failure) and 7 agent/API tests.

**Security changes:** host allow-list and robots/rate-limit compliance for official sources;
digit-only document IDs; sync owner-triggered, rate-limited and audited; unverified sources
cannot be enabled; OpenCode isolation rules written down before any integration.

**User-visible changes:** with `EZO_OFFICIAL_SOURCES=lexuz` and synchronized acts, legal
questions are answered from official texts with full metadata and a live currentness check.
Without it, EZO says that no official texts are synchronized.

**Known limitations (honest):** **no live LEX.UZ traffic has ever happened**. lex.uz was
unreachable from the build environment, so robots.txt and the terms are unverified, and the
connector has only parsed synthetic test pages (the real LRU-682 number and date, with
illustrative article text). Other sources have no connector. There is no change feed, so new
acts are added by ID. No scheduler until Phase 5. Publication and effective dates are not
extracted. Official texts are per user (single-owner EZO). The OpenCode V2 docs were
unreachable, and its full dependency-licence scan is pending.

**How the owner can test:** follow `docs/OFFICIAL_SOURCES.md` → *Enabling LEX.UZ*: review the
terms and robots.txt, set `EZO_OFFICIAL_SOURCES=lexuz`, sync `5695915`, compare
`GET /api/official/documents/{id}` with the lex.uz page, then ask the legal question in chat.

## Phase 2 — Visual Agent (2026-10-18) — alpha

*(Called "Phase 6" before the 2026-10-18 renumbering.)*

**What changed**
- Image providers behind `ImageProvider` / `ImageEditProvider`: OpenAI (Images API) and
  Gemini (image output) adapters; model IDs, quality and limits are settings
  (`EZO_IMAGE_*`). `VisualService` falls back in order but never after a content-policy
  refusal, and re-encodes every returned image (format allowlist, pixel cap, metadata
  stripped).
- `VisualAgent` (alpha): images, hero and product visuals, edits of the conversation's image
  or an uploaded image, diagrams, social graphics (square / 4:5 / story / landscape), logo
  concepts with variants. One cheap `chat`-route call writes the prompt or spec; no call is
  made when a picture is needed but no provider exists.
- EZO draws all text: diagrams through the slide engine (PNG + SVG), social graphics and logo
  sheets with EZO fonts. Without a provider the picture is an abstract placeholder recorded as
  `placeholder: true` with a reason.
- Every output is a versioned `image` artifact (edits add versions) with provider, model,
  prompt, revised prompt, dimensions, quality, attempts, conversation and project; uploads
  keep a source reference.
- Presentations: new `ImageBox` primitive in PPTX/PDF/PNG/HTML; hero slides get generated
  images (`EZO_IMAGE_MAX_PER_DECK`), reused when a deck is edited; model-written image ids
  are discarded and only the user's own image artifacts are loaded; story scenes link them.
- Routing: broader uz/en/ru visual signals; "fonini ko'k qil" after an image edits it.
  `/api/status` lists `image_providers`; `visual` feature is alpha.
- Web: image preview in the chat card; artifacts page shows the preview, how it was made, or
  the placeholder notice; uz/en/ru strings.
- Roadmap renumbered to the 2026-10-18 master prompt (catalog and features follow).

**Files added:** `apps/api/src/ezo_api/visual/{base,images,openai_images,gemini_images,service,compose,kinds}.py`,
`apps/api/src/ezo_api/agents/visual.py`, `apps/api/src/ezo_api/tools/visual_tools.py`,
`apps/api/tests/unit/test_visual.py`, `apps/api/tests/integration/test_visual_agent.py`,
`apps/web/components/artifacts/VersionExports.test.ts`, `tests/e2e/specs/visual.spec.ts`,
`docs/VISUAL_AGENT.md`.
**Files modified:** slide engine (primitives, layouts, QA, build, spec, PPTX/PDF/PNG/HTML
renderers), PresentationAgent, `create_presentation`, story-from-deck, EzoCore routing,
intent rules, agent registry and catalog, `maturity.py`, settings, services, status schema
and route, test fakes and four existing tests (a planned agent is now Business, not Visual),
web artifact card/page/exports, i18n, shared types, `.env.example`, ROADMAP, README,
ARCHITECTURE, TROUBLESHOOTING, `docs/SECURITY.md`, `docs/LANGUAGE_COACH.md`.
**Database migrations:** none (`image` was already an artifact type; `alembic check` clean).

**Tests added:** 22 unit test cases (image safety: crop, re-encode, EXIF removal, non-images,
decompression bombs, downscaling; request rules; OpenAI and Gemini adapters incl. refusals;
fallback order and refusal stop; settings → providers; diagram/social/logo layouts; slide
images in every format; placeholder QA; image-id validation) and 10 integration tests
(generate + follow-up edit as version 2, no provider = no call and nothing stored, diagram
without provider, labelled social placeholder, logo variants + text edit reusing the symbol,
final refusal, upload edit, deck images generated and reused on edit, deck without provider,
status); one web unit test; one Playwright spec (2 tests).

**Security changes:** untrusted image gate (decode, allowlist, 25 MB / 40 MP, re-encode);
SVG only as a sandboxed attachment; model-written artifact ids discarded and ownership checked
before an image is embedded; refusals never routed around; per-request and per-deck limits
for paid image calls.

**User-visible changes:** ask for an image, a diagram, a social graphic or a logo in chat;
image previews in chat and on **Yaratilganlar**; picture slides in presentations.

**Known limitations:** rule-based kind/edit detection; diagrams limited to the slide engine's
flow/process/timeline layouts; no masks, upscaling or transparent exports yet; only hero
slides get generated images; image generation runs inside the chat request (durable jobs are
Phase 5); the adapters are tested with SDK-shaped fakes, not against live provider accounts
(no keys in CI). See `docs/VISUAL_AGENT.md`.

**How the owner can test:** put `OPENAI_API_KEY` (or `GEMINI_API_KEY`) in `.env`, restart,
then in chat: “Kosmosdagi mushuk rasmini chiz” → “Fonini to'q ko'k qil” → open
**Yaratilganlar** (two versions). Without a key: “EZO arxitekturasi diagrammasini chiz”
still works, and “Instagram story tayyorla” shows a labelled placeholder.

## Phase 5 — Language Coach + IELTS-style simulator (2026-10-17) — alpha

*(Phase 1 after the 2026-10-18 renumbering.)*

**What changed**
- `LanguageCoachAgent`: real practice sessions with recorded learner and coach turns,
  computed metrics, a validated assessment, recurring-mistake tracking, goals, vocabulary and
  progress over time. EZO stays one assistant: an active session keeps ordinary English
  answers with the coach ("sticky" routing) until it is finished.
- Modes: free conversation, IELTS-style speaking (Part 1 → Part 2 task card → Part 3, with
  original questions), teacher, grammar, vocabulary, debate, job interview, travel, business
  English. CEFR adaptation from the request or the active goal.
- Assessment once per session on the `reasoning` route; practice turns on the cheap `chat`
  route. Model output is checked by rules: bands rounded and clamped, estimated range from the
  criteria mean (wider below 150 words), no band below 40 learner words, mistakes kept only if
  the learner really said the quoted text, unknown categories mapped to `other`.
- Exact computed metrics: words, moving-window lexical diversity, fillers per 100 words,
  repeated words, words per minute (only from measured voice time).
- Report artifact (DOCX with PDF and Markdown exports) in uz/en/ru.
- Web: “Til mashg'ulotlari” page (goal, trends, recurring mistakes, sessions, vocabulary,
  reports, delete with confirmation); voice turns send their measured speaking time.

**Files added:** `apps/api/src/ezo_api/db/models/language.py`,
`apps/api/migrations/versions/0004_language_coach.py`,
`apps/api/src/ezo_api/language/{analysis,modes,ielts,assessment,service,report}.py`,
`apps/api/src/ezo_api/agents/language_coach.py`, `apps/api/src/ezo_api/schemas/language.py`,
`apps/api/src/ezo_api/api/routes/language.py`, `apps/api/tests/unit/test_language.py`,
`apps/api/tests/integration/test_language_coach.py`,
`apps/web/components/language/LanguagePage.tsx` (+ test), `apps/web/app/language/page.tsx`,
`tests/e2e/specs/language.spec.ts`, `docs/LANGUAGE_COACH.md`.
**Files modified:** EzoCore (sticky routing, `speech_seconds`), intent rules, agent catalog,
`maturity.py`, chat schema and route, `main.py`, voice VAD/engine/speech, VoiceStage,
useChatSession, shared types and API client, history navigation, i18n (uz/en/ru), voice e2e
spec, README, ARCHITECTURE, TROUBLESHOOTING, ROADMAP.
**Database migrations:** `0004_language_coach` — `language_sessions`, `language_turns`,
`language_metrics`, `language_mistakes`, `language_goals`, `language_vocabulary`.

**Tests added:** 17 unit tests (metrics, mode/level/command/goal detection, IELTS flow, band
rounding and ranges, validation, localised honest report) and 5 integration tests (full
three-part simulator with assessment and report, free practice + finish + progress +
recurring mistakes, goals/API/privacy delete, too little speech, offline mode); one web unit
test; one Playwright spec; the voice e2e spec checks the measured speaking time.

**Security changes:** language data is per user (every query filtered by user); deleting a
session needs `?confirm=true` and removes its transcript, metrics and mistakes; raw audio is
never stored; the transcript is passed to the assessor as delimited data.

**User-visible changes:** say “IELTS speaking qilamiz” or “English speaking qilamiz” in chat
or voice; “Feedback ber” finishes a session; progress questions answer from stored results;
new “Til mashg'ulotlari” page.

**Known limitations:** English only; rule-based mode/command detection; the Part 2
preparation minute is not timed; pronunciation is transcript-assisted at best (acoustic
analysis is planned with realtime voice); bands are practice estimates, not calibrated
against real exam results. See `docs/LANGUAGE_COACH.md`.

**How the owner can test:** with an API key, open chat → “IELTS speaking qilamiz, B2
darajada” → answer the questions (typing or **Gaplashish**) → after Part 3 EZO gives
feedback and a report card → open **Til mashg'ulotlari**.

## Phase history (records made at the time)

Numbers in this history are the **local** results recorded when each phase finished. They
come from different environments and are not comparable with each other or with CI. Use
*Latest verified baseline* for current numbers.

### Baseline before Milestone 2 (2026-10-17, commit `b5d16c6`)

| Check | Result |
|---|---|
| Backend lint (`ruff check`) and format check | ✅ pass |
| Backend types (`mypy --strict`) | ✅ pass (61 files) |
| Backend tests on SQLite | ✅ 101 passed |
| Backend tests on PostgreSQL 16 | ✅ 101 passed |
| Frontend lint, type-check | ✅ pass |
| Frontend unit tests (Vitest) | ✅ 14 passed |
| Web production build | ✅ pass |
| Browser end-to-end tests (Playwright) | ✅ 9 passed |
| Docker images | ✅ built and stack ran (verified in the previous session; this cloud sandbox needs its proxy certificate added to temporary copies of the Dockerfiles) |

Milestone 1 features present and covered by tests: streaming chat, conversations, projects,
profile/project memory, EzoCore pipeline with intent routing and traces, provider abstraction
(Anthropic, OpenAI, Gemini, offline) with routing and fallback, personality engine,
browser voice conversation, uz/en/ru UI, auth (local/token), rate limiting, audit log.

Not yet implemented at baseline: Milestones 2–8 (see ROADMAP.md).

### Knowledge (Milestone 2) — verified 2026-10-17

| Check | Result |
|---|---|
| Backend lint + format (`ruff check` / `ruff format --check`, incl. scripts) | ✅ pass |
| Backend types (`mypy --strict`) | ✅ pass (101 files) |
| Backend tests on SQLite | ✅ 211 passed, 1 skipped (the pgvector-only test) |
| Backend tests on PostgreSQL 16 + pgvector | ✅ 212 passed |
| Migrations: fresh install, 0001 → 0002 upgrade with data, `alembic check`, downgrade | ✅ SQLite and PostgreSQL (with and without permission to create the `vector` extension) |
| Frontend lint + type-check | ✅ pass |
| Frontend unit tests (Vitest) | ✅ 38 passed (shared 9, web 29) |
| Web production build | ✅ pass (new route `/knowledge`) |
| Browser end-to-end tests (Playwright) | ✅ 15 passed (chat, voice, memory, projects, settings, mobile, presence states, files) |
| Docker | ✅ API and web images built; API container migrated a fresh PostgreSQL to 0002, used pgvector, ingested an upload into the `ezo-storage` volume as the non-root user, keyword search returned it; web container served `/` and `/knowledge` |

Docker note: this cloud sandbox reaches the internet through a proxy with its own certificate,
so verification builds used temporary copies of the Dockerfiles that add that certificate
(`--build-context ca=…`). The Dockerfiles in the repository are unchanged in that respect.

#### What works

Upload (paperclip or **Files** page) → validated, stored, read in the background → searchable
by keywords (always) and meaning (with an OpenAI/Gemini key) → EZO answers with numbered,
verified citations and lists the sources under the answer. Changed files become new revisions.
Web research via Claude web search or Tavily with official-source preference and dated citations.
Memories are retrieved semantically when embeddings are available. The orb shows real activity
(searching, reading…). Details: README “Files, knowledge and research”.

#### How to test

```bash
python scripts/ezo.py test --e2e                                   # everything
EZO_TEST_DATABASE_URL=postgresql://ezo:ezo@localhost:5432/ezo_test \
  uv run --project apps/api pytest apps/api/tests                  # backend on PostgreSQL
```

Manually: open **Files**, drop a PDF, wait for **Tayyor/Qisman**, then ask a question about it
in chat — the answer cites `[1]` and shows the source under it.

#### Configuration

`TAVILY_API_KEY`, `EZO_WEB_SEARCH_PROVIDER`, `EZO_WEB_SEARCH_MODEL`, `EZO_STORAGE_DIR`,
`EZO_MAX_UPLOAD_MB`, `EZO_VECTOR_STORE`, `EZO_INGESTION_MODE`, `EZO_FETCH_ALLOW_PRIVATE_NETWORKS`
(see `.env.example`); embedding models in `apps/api/config/models.toml` → `[[embeddings.candidates]]`.

#### Known limitations

No OCR (images/scans → “needs OCR”), no Qdrant or S3 implementations yet (interfaces exist),
ingestion runs inside the API process, some API messages are English-only, the reranker is a
pass-through. See ROADMAP “Known limitations”.

#### Security considerations

Content-sniffed uploads with size and zip-bomb limits; storage keys cannot escape the storage
folder; SSRF-safe fetching (private/loopback/link-local/CGNAT refused on every redirect,
robots.txt, size/type/time limits); source text treated as data (prompt-injection guard);
tool calls validated, time-limited, dangerous tools denied, every call audited with secrets
redacted; ownership checks on every document; uploads audited.

#### Quality gate

1. **Does it actually run?** Yes — API and web run locally and in Docker; upload → search → cited answer verified.
2. **Are tests passing?** Yes — numbers above, SQLite and PostgreSQL.
3. **Does Docker still work?** Yes — both images built and ran (see note on the sandbox certificate).
4. **Are migrations valid?** Yes — fresh install, upgrade from 0001 with data, `alembic check` clean, downgrade works.
5. **Does Milestone 1 still work?** Yes — all Milestone 1 tests and e2e specs still pass.
6. **Security regressions?** None found; new attack surfaces (uploads, URL fetching, tools) have dedicated protections and tests.
7. **Faked functionality?** No — OCR, Qdrant, S3 and model reranking are explicitly reported as not implemented; without embeddings or web search EZO says so.
8. **Understandable to a beginner?** Yes — one Files icon, a paperclip, status badges in Uzbek, and README/TROUBLESHOOTING sections in plain language.

### Voice / presence (open-source integration) — 2026-10-17

- ✅ Licence audit: [docs/OPEN_SOURCE_AUDIT.md](docs/OPEN_SOURCE_AUDIT.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- ✅ Phase 1 — EZO presence states (original code; unit, render and e2e tests).
- ✅ Phase 2 — voice providers (details below).

#### Voice providers — verified 2026-10-17

**What was changed:** new `voice/` package in the API (interfaces, OpenAI-compatible adapter,
fallback service), `/api/voice/status|transcribe|speak`, voice settings, an optional
`voicestudio` service in a `voice` Docker Compose profile, and a web voice engine (recording
with pause detection, server speech, automatic browser fallback). Settings → System status
shows the active voice.

**Code reused:** none. VoiceStudio (AGPL-3.0) is called over its documented OpenAI-compatible
HTTP API from a separate container; its source is not part of EZO. Everything else was written
from scratch.

**Tests:**

| Check | Result |
|---|---|
| Backend lint/format/mypy | ✅ pass (108 files) |
| Backend tests SQLite / PostgreSQL | ✅ 235 passed + 1 skipped / 236 passed |
| — voice unit tests | audio sniffing, adapter, error mapping, fallback order, `bad_audio` stop, configuration, **wire-format contract with the real OpenAI SDK** (paths, Bearer key, multipart, `language` field) |
| — voice API tests | no provider → 503 with hint; fallback with attempts; non-audio → 422; oversized → 413; speak MP3 + `no-store`; all failing → 502; audio never written to disk/DB; transcript → voice chat message |
| Frontend lint/typecheck/unit | ✅ pass; 43 unit tests (incl. pause detection) |
| Web production build | ✅ pass |
| Playwright | ✅ 17 passed, incl. server voice round trip with a synthetic microphone, tap-to-interrupt while EZO speaks, and server failure → browser listening and speaking |
| Docker | ✅ API image rebuilt and run: `/api/voice/status` lists VoiceStudio; with VoiceStudio unreachable, transcribe returns a clear 502 with the failed attempt. `docker compose config` valid with and without `--profile voice` |

**Known limitations:** the VoiceStudio container itself could not be started in this sandbox
(its registry is blocked by the sandbox proxy), so VoiceStudio was verified by the contract test
against its documented API, not live. Voice is turn-by-turn, not realtime streaming (the
`RealtimeVoiceProvider` interface exists without an implementation, Milestone 7). Pause
detection is a simple energy threshold (noisy rooms may end a turn late). VoiceStudio’s default
voice model is non-commercial.

**How the owner can test:** with `OPENAI_API_KEY` set, open **Gaplashish**, tap the robot, speak
a sentence and pause: EZO answers with OpenAI’s voice; tap while it speaks to interrupt. Without
keys the browser voice is used as before. For VoiceStudio see README → *Optional integrations*.

### Artifacts (Phase 3) — verified 2026-10-17

**What was changed:**
- Migration 0003 adds artifacts, immutable artifact versions and the story project tables.
- `ArtifactService`, `StoryService` and the timeline planner.
- `/api/artifacts`: list with filters, details, create from text or a message, rename, edit
  as a new version, restore, download, text preview and confirmed delete.
- `/api/stories`: CRUD, replacing scenes, reordering, timeline.
- Chat answers can be saved, and artifacts appear as cards under answers.
- New “Yaratilganlar / Created” page and history-panel icon, with uz/en/ru texts.
- CORS fix: the browser can now read download filenames, and PUT is allowed.

**Code reused:** none. Built on EZO’s existing StorageProvider and audit log.

| Check | Result |
|---|---|
| Backend lint/format/mypy | ✅ pass (118 files) |
| Backend tests SQLite / PostgreSQL | ✅ 252 passed + 1 skipped / 253 passed |
| — artifact tests | creation, download headers, edit → v2 with v1 preserved, identical content = no version, restore → v3 with parent, rename, filters, confirmed delete + storage cleanup, project deletion keeps artifacts, other users’ artifacts → 404 on every route, save answer from message (sources + message card), unsafe types/empty/unknown type rejected, path tricks sanitised, CORS exposure |
| — story tests | CRUD, ordering, invalid reorder, scene replacement, narration-aware timeline, assets limited to own artifacts, access control, project scope; timeline unit tests |
| Migrations | ✅ SQLite + PostgreSQL: fresh install, upgrade 0002 → 0003 (also on a database with existing data), `alembic check`, downgrade + re-upgrade |
| Frontend lint/typecheck/unit | ✅ pass; 46 unit tests |
| Web production build | ✅ pass (new route `/artifacts`) |
| Playwright | ✅ 18 passed, incl. save answer → card → Created → edit (v2) → restore (v3) → download → rename → delete |
| Docker | ✅ API image rebuilt; container migrated a fresh PostgreSQL to 0003; created an artifact, added v2, downloaded v1 unchanged; both versions stored in the volume |

**Quality gate:**
1. Runs? Yes, locally and in Docker.
2. Tests pass? Yes (numbers above).
3. Docker? Yes.
4. Migrations valid? Yes.
5. Chat, RAG and voice still work? Yes, all earlier tests and e2e pass.
6. Old versions preserved? Yes. Versions are never updated, restore appends, and tests check
   old content byte for byte.
7. Provenance? Yes. Each version records the parent version, creator, provider, model and
   sources. Saved answers keep their citations.
8. Failures reported honestly? Yes: missing file → 410, non-text edit → 409, unsupported type →
   422, other users → 404.
9. Security? Yes: owner scoping, sanitised names, content-addressed keys, server-decided MIME
   types, download headers, confirmed and audited deletes.
10. Beginner can test? Yes: press *Saqlash* under an answer, then open *Yaratilganlar*.

**Known limitations:**
- Only text artifacts can be edited in the UI. Binary files (PPTX, images) get new versions
  from the agents in later phases.
- Story projects have no UI of their own yet; they are used internally by Phase 4.
- Artifacts are stored locally. S3 storage is still interface-only.

### Documents + Presentations (Phase 4) — verified 2026-10-17

**What was changed:**
- `documents/`: format services (DOCX, PDF with bundled Liberation Sans, XLSX/CSV with a
  formula-injection guard, Markdown/TXT, spreadsheet analysis, diff, `OCRProvider` interface).
- `documents/render/`: own slide engine. 24 layouts, 5 themes, real font-metric text fitting,
  PPTX/PDF/HTML/PNG renderers from one layout plan, layout QA.
- Artifact **exports** per version (PDF, web, Word, Markdown, CSV, previews, deck spec), with
  a download endpoint and cleanup on delete.
- Tools: `read_document`, `create_document`, `create_spreadsheet`, `create_presentation`.
- `DocumentAgent` and `PresentationAgent` (catalog: available). Intent signals updated
  (presentation wins ties; translation/report/official-letter signals for documents).
- Web: “Other formats” downloads, slide thumbnails and QA result on the Created page.

**Code reused:** none copied. Libraries: python-pptx, reportlab, Pillow (new); python-docx,
openpyxl (existing). Liberation Sans fonts bundled under OFL 1.1 (see THIRD_PARTY_NOTICES).

| Check | Result |
|---|---|
| Backend lint/format/mypy | ✅ pass (151 files) |
| Backend tests SQLite / PostgreSQL | ✅ 310 passed + 1 skipped / 311 passed |
| — engine | every layout rendered; PPTX re-opened (python-pptx) and opened by LibreOffice; native charts with exact values; bullets via `buChar`; QA detects empty/overflow/duplicate/chart/table problems with slide numbers |
| — agents | file-based deck with sources slide and citations; reasoning route for the deck, chat route for the report; follow-up edit → v2 with story updated and v1 exports intact; QA repair round; invalid model output → nothing created, honest note; offline → nothing created; DOCX creation with placeholders; translation → derived artifact, original unchanged; follow-up rewrite → v2; comparison; spreadsheet facts; XLSX creation with empty unknowns and neutralised formulas; project scope; offline conversion |
| Frontend lint/typecheck/unit | ✅ pass; 46 unit tests |
| Web production build | ✅ pass |
| Playwright | ✅ 19 passed, new: attach file → “PDF ga aylantir” → PDF download → Word export download |
| Docker | ✅ API image rebuilt; inside the container: deck → PPTX + PDF + 2 previews, QA passed; DOCX/PDF/MD rendered; catalog lists document + presentation |
| Migrations | no schema change in this phase (exports live in version metadata) |

**Quality gate:**
1. Runs? Yes, locally and in Docker.
2. Tests pass? Yes (numbers above).
3. Docker? Yes.
4. Migrations valid? No new migration; 0003 unchanged and still verified by the suite.
5. Chat, RAG, research and voice still work? Yes, all earlier tests and e2e pass.
6. Old versions preserved? Yes. Edits and regenerations add versions, exports are per version,
   and tests read v1's spec after v2 exists.
7. Provenance? Yes: provider, model, `derived_from`, change summary, diff statistics, QA report
   and sources on every generated version.
8. Failures honest? Yes: no file → asks for upload; invalid model output, provider failure or
   offline → “nothing was created”; remaining QA issues are reported with slide numbers.
9. Security? Yes: owner + project scoping, source text wrapped as data in prompts, formula
   injection neutralised, server-decided MIME types, exports never rendered in the API origin.
10. Beginner can test? Yes: try the examples in README → *Documents and presentations*.

**Known limitations:**
- No image generation yet (abstract visuals on image slides); no OCR for scans.
- Conversion of uploaded PDFs/DOCX carries the text, not the original page layout.
- Long files: transformations process the first 40,000 characters and say so.
- Story projects still have no dedicated UI.

### Orchestration foundation + Ruflo audit — 2026-10-17

**What was changed:**
- `docs/OPEN_SOURCE_AUDIT.md` § 6 records the Ruflo audit: licence, security findings and
  decision.
- `docs/RUFLO_INTEGRATION_PLAN.md` covers architecture, security boundary, MCP strategy,
  allow-list, mission schema, lifecycle, approvals, fallback, UI, testing and deployment.
- `orchestration/`:
  - the `OrchestrationProvider` interface;
  - a working `NativeOrchestrationProvider`;
  - deterministic complexity routing and plan drafts;
  - the `AgentOutput` contract;
  - the security boundary: allow-list, deny-list, redaction, hardened environment.
- Settings: `EZO_ORCHESTRATION_PROVIDER`, `EZO_RUFLO_ENABLED`, `EZO_RUFLO_COMMAND`,
  `EZO_RUFLO_TIMEOUT_SECONDS`. Ruflo is off by default and falls back to native with a notice.

**Deliberately not done yet (per the roadmap):** missions are not started from chat. There are
no mission tables, no `RufloProvider` and no MCP client yet. Ruflo was not installed or
initialised anywhere, and no plugins or mods were enabled. No Ruflo code was copied.

| Check | Result |
|---|---|
| Backend lint/format/mypy | ✅ pass (158 files) |
| Unit tests (orchestration) | ✅ 25 tests: interface, routing on the spec examples, plan validation, lifecycle, parallelism, scoped inputs, retries, failure propagation, invalid output, timeouts, approve/reject, pause/resume, cancel, ownership, artifact linking, presence events, allow-list/deny-list, redaction, hardened environment, Ruflo fallback |
| Integration (realistic mission) | ✅ research → DOCX report via real tools → PPTX from both structured outputs → QA; mission completed, both artifacts linked and listed |

**Quality gate:**
1. Runs? Yes. Nothing user-visible changed, so chat is unchanged.
2. Tests pass? Yes (see the full suite numbers in the commit log).
3. Docker? Yes. No new dependency; the API image is unchanged.
4. Migrations? None needed yet; the mission tables are specified in the plan.
5. Existing features intact? Yes, all earlier tests pass.
6–7. Versions and provenance? Mission artifacts are ordinary versioned artifacts.
8. Honest failures? Yes. A mission fails when any step or the QA fails. Ruflo being
   unavailable falls back to native with a plain notice.
9. Security? Yes: allow-list plus hard deny-list, no secrets passed, isolated HOME, opt-outs
   for self-update, daemon and promo feeds, stdio only, and approval gates for actions with
   outside effects.
10. Beginner? Nothing to configure; see README → *Ruflo*.

## Next step

Knowledge OS & SkillForge (owner prompt of 2026-10-19), starting with K1 — source registry
and secure ingestion. Government work mode E2–E4 (secretary, citizen appeals, reports)
remain open after E1.
Owner decisions still open: a licence, a protected `main` branch, the Dependabot PRs, and
the LegalResearchAgent visibility
([docs/OFFICIAL_KNOWLEDGE_INTEGRATION_PLAN.md](docs/OFFICIAL_KNOWLEDGE_INTEGRATION_PLAN.md) §6).
Ruflo stays off (Phase 14).
