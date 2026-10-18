# Document fidelity: editing Word files without breaking them

When a user asks EZO to translate, proofread, formalize or rewrite a `.docx`, EZO
edits **the original file in place**. It does not regenerate the document from
Markdown. The model never sees or writes the file format; it only sees and returns
paragraph texts. `apps/api/src/ezo_api/documents/docx/fidelity.py` writes them back.

## How it works

1. **Read.** Every paragraph is collected: body, table cells, text boxes, headers and
   footers. Its *runs* (pieces of text with one formatting) are grouped into
   *segments* of identical formatting (font, size, bold, colour, link...).
2. **Encode.** For the model each paragraph becomes one line, `[[n]] text`. Text whose
   formatting differs from the paragraph's main formatting gets markers:
   `Ijara narxi ⟦1⟧4 500 000 so'm⟦/1⟧ bo'lib…`. Tabs and line breaks become `⟨TAB⟩` and
   `⟨BR⟩`. Paragraphs with no letters (`________`, numbers only) are not sent.
3. **Batch.** Paragraphs go out in batches of about 6,000 characters. There is no
   40,000-character cut-off: the whole document is processed, up to 400,000
   characters (~150 pages) per request. A longer file is refused with an explanation,
   never silently shortened.
4. **Write back.** Each new text is put into copies of the paragraph's own runs:
   - with valid markers, every marked part gets its original formatting;
   - with missing or broken markers, small edits are mapped onto the runs character by
     character (difflib), so a proofread keeps the bold word bold;
   - only when neither works does the paragraph fall back to its main formatting.
     This is counted and reported as a warning.
5. **Verify.** A structural inventory is taken before and after (paragraphs, tables
   and cells, images, sections, page setup, paragraph styles, numbering, hyperlinks,
   bookmarks, comments, fields, headers, footers, and a hash of `styles.xml`). Any
   difference is reported to the user and stored in the artifact metadata.

For translations the model must return every paragraph. Paragraphs it leaves out are
sent again once. If they are still missing they stay in the original language and the
user is told how many.

## What is kept

The test fixture (`tests/docx_fixtures.py`) contains a Heading 1, a bold amount inside
a sentence, a hyperlink, italic red text, a numbered list, a table, an image, a header
and a footer with a PAGE field. After an English translation
(`tests/unit/test_docx_fidelity.py`, `tests/integration/test_docx_office.py`) **all**
of these were verified to be unchanged:

| Property | Result |
| --- | --- |
| Paragraph count, table count and cells, image count | identical |
| Styles (`styles.xml` byte-identical), paragraph styles (Heading 1, List Number) | identical |
| Bold amount inside the sentence | still bold, around the translated words |
| Italic red "Important:" | italic, colour C00000 kept |
| Hyperlink | same link target, translated link text |
| Header and footer | translated; the PAGE field is still in the footer |
| Page size, orientation, margins, sections | identical |
| LibreOffice opens the result | yes (converted to PDF in the test) |

The uploaded original is never modified. An upload yields a **new** artifact
(`shartnoma (en).docx`); an EZO document yields a **new version** of the same artifact.

## What is not changed (and reported)

Paragraphs containing complex fields (tables of contents, cross-references), existing
tracked changes, content controls, custom XML, smart tags or equations are left as
they are. The reply says how many were skipped and why. Simple fields such as a PAGE
number stay in place and the text around them is edited.

Footnotes, endnotes and comment texts are not edited. Text inside charts and
SmartArt is not edited either.

## Tracked changes

When the user asks for it ("track changes", "o'zgarishlar ko'rinsin", "tahrir rejimida",
"в режиме правок"), edits are written as **real Word revisions** (`w:del` / `w:ins`, author
"EZO", with a date) that can be accepted or rejected in Word or LibreOffice:

- **word level** for paragraphs with uniform formatting: only the changed words are
  marked;
- **paragraph level** otherwise: the old paragraph text is marked deleted and the new
  text inserted.

This is what EZO supports. It is not every Track Changes feature of Word: there are no
formatting-change revisions, no moves and no comments.

## Find and replace (no model, no API key)

`«Ijarachi» ni «Arendator» ga almashtir` / `replace "X" with "Y"` / `замени «X» на «Y»`
replaces text everywhere in the Word file: body, tables, headers and footers. It also
works when the text is split across differently formatted runs, and formatting is kept.
Tracked changes are available here as well. If the text is not found, nothing is saved
and the user is told so.

## Safety

- Files over 50 MB or that are not valid `.docx` packages are refused.
- Macros are never executed. `.docm` files are not accepted for upload.
- The reply checks numbers. If the digits in a paragraph differ after a translation or
  proofread, the paragraph is flagged as a warning.
