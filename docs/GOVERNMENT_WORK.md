# Government work mode

Status: **E1 Organization profiles — alpha**. E2 (secretary: meeting minutes and task
registers), E3 (citizen appeals) and E4 (reports) are **not built yet**.

Everything runs through the normal chat; there is no separate "government" chatbot. EZO
writes **drafts**: an official paper becomes official only after an authorized person
reviews, signs and registers it. EZO never produces signatures, seals, approval marks or
registration numbers, and never invents legal facts, decisions or personal details.

## E1 — Organization profiles

Settings → **Tashkilot profili**. One profile is the default; EZO uses only what you
enter there.

| Part | What it does |
| --- | --- |
| Name, type, department, address, contacts, head's position and name | Letterhead lines and the signature block of official papers |
| Letterhead lines | Your own wording of the letterhead (one line per row) |
| Style notes | House style sent to the writer ("Qisqa va aniq yozamiz") |
| Terminology (`mutasaddi = mas'ul`, one per line) | Preferred terms in letters, documents, presentations and translations |
| **Document formatting** | Font, size (8–20 pt), line spacing, first-line indent, margins (A4). Default: Times New Roman 14, 1.15, 1.25 cm, margins 2/2/3/1.5 cm |
| **Logo** | PNG, JPEG or WebP up to 5 MB, re-encoded by EZO to a clean PNG (≤600 px); printed on the letterhead |
| **Approved templates** | Your official blank as `.docx`, for one document type or for all official papers |
| **Example documents** | DOCX, PDF, TXT or Markdown examples of your style |
| **Export** | One ZIP: `profile.json`, `logo.png`, `templates/`, `examples/` |
| **Delete** | Removes the profile, its stored files and its glossary terms (asks first) |

### Approved templates

Write `{{matn}}` (or `{{text}}`, `{{матн}}`, `{{текст}}`) in the template where the text
belongs. EZO keeps everything before the marker (letterhead, logo, tables), removes the
marker and any sample text after it, and writes the document there. Without a marker the
whole template body stays and the text follows it. The template's header, footer, styles
and margins are kept; EZO adds only the **QORALAMA** (draft) label to the header.

A template is used for official layouts (letters, acts, minutes, orders…). A template for
the requested document type wins over a general one. Templates with macros or external
links (remote images, linked files) are refused.

### Examples

Up to two examples (same document type first) are sent to the writer as **style
references** inside `<example>` tags, with the instruction never to copy their names,
dates, numbers or decisions. They are not evidence: a number that appears only in an
example and not in your request is flagged in the result for you to check.

### Try in chat

| Try | Result |
| --- | --- |
| "Ezo, tashkilotimiz blankasida xizmat xati tayyorla: …" | Word (+ PDF) in your approved template, or on EZO's letterhead with your logo and formatting; examples used for style |
| "Ташкилотимиз бланкасида хизмат хати тайёрла: …" | The same in Uzbek Cyrillic |
| "Tashkilotimiz blankasida xodimlar uchun yo'riqnoma hujjatini yarat" | Any other document with the letterhead (logo, lines, contacts) and your formatting |
| "Tashkilotimiz faoliyati haqida taqdimot tayyorla" | Slides that use the organization's name (cover), style and terms |
| "Xizmat xati shablonini ber" (or no AI key) | The empty template with placeholders, in your approved blank |

"Blankasida" / "на бланке" means *on our letterhead, with content*; "shablon" / "blank
ber" means an empty template.

### API

| Method | Path | Notes |
| --- | --- | --- |
| GET / POST | `/api/writing/organizations` | list / create (with `formatting`) |
| PUT / DELETE | `/api/writing/organizations/{id}` | update / delete with all files |
| PUT / GET / DELETE | `/api/writing/organizations/{id}/logo` | image upload (multipart `file`), PNG out |
| GET / POST | `/api/writing/organizations/{id}/files` | list / upload (`file`, `kind` = template \| example, `title`, `doc_type`) |
| GET | `/api/writing/organizations/{id}/files/{file_id}/download` | the stored file |
| DELETE | `/api/writing/organizations/{id}/files/{file_id}` | remove one file |
| GET | `/api/writing/organizations/{id}/export` | ZIP |
| GET | `/api/writing/document-types` | document types (for the template's type) |

### Data protection

- Profiles and files belong to one user; every endpoint checks ownership (others get 404).
- Uploads: 10 MB per file (logo 5 MB), type detected from content, not the name; the logo
  is decoded and re-encoded; templates are opened and checked before they are stored;
  example text is read by EZO's own parsers. Downloads are sent with `nosniff`, a
  sandboxing CSP and `no-store`.
- Contents of templates and examples are **untrusted data**: they are never followed as
  instructions, and only short excerpts of examples (3000 characters each) reach the AI
  provider, inside the user's own drafting request.
- Every change (create, update, logo, file add/remove, export, delete) is audit-logged.
- Do not upload documents with citizens' personal data as examples unless your
  organization allows sending them to the configured AI provider.

### Limits

- One default profile is used in chat; there is no profile switching by name yet.
- Templates must be `.docx`; `.doc`, `.dotx` and PDF blanks are not accepted.
- Complex templates (text boxes, sections with different headers) keep their layout, but
  EZO writes only into the main body at the marker.
- Logos are placed only on EZO's own letterhead; an approved template keeps its own logo.
- The PDF, Markdown and text versions carry the letterhead as text lines, not the logo.
- Profiles cannot be imported from an export ZIP yet.
