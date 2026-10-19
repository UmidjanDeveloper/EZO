# Professional writing

EZO drafts official, academic, career and public documents in natural Uzbek (Latin or
Cyrillic), Russian or English, in the layout people expect. It never invents a name,
date, number, legal ground or signature.

## Ask in chat

| Try | Result |
| --- | --- |
| "Shu faktlar asosida tushuntirish xati yoz va Word qilib ber: …" | Draft in official layout: DOCX + PDF + .md + .txt |
| "Tashkilotimiz uslubida viloyat hokimligiga xizmat xati tayyorla: …" | Uses your organization profile (letterhead, contacts, house style, preferred terms) |
| "Yig'ilish bayonnomasi shablonini tayyorla" | Template with placeholders — **no AI model, no cost** |
| "Qisqa, rasmiy, kirillda yoz", "300 so'zli", "2 betlik", "ruscha" | Length, mode and language options |
| "qoralama belgisisiz" | Leaves out the QORALAMA header line |

Without any AI key EZO still produces the **template** for any type, and says so.

## Document types (30)

Official: ariza, tushuntirish xati, bildirishnoma, xizmat xati, rasmiy murojaat, javob
xati, ma'lumotnoma loyihasi, taqdimnoma, dalolatnoma, bayonnoma, yig'ilish protokoli,
buyruq loyihasi, qaror loyihasi, hisobot, ish rejasi, xulosa, ishonchnoma loyihasi.
Business and public: taklif xati, taklifnoma, tabriknoma, ma'ruza, nutq, press-reliz,
e'lon, tadbir dasturi. Career and academic: CV, motivatsion xat, cover letter,
tavsiyanoma, ilmiy tadqiqot taklifi. The full list with fields and sections is at
`GET /api/writing/document-types` (source: `apps/api/src/ezo_api/writing/catalog.py`).

## How a draft is made

1. **Recognise** the type and options from the request (deterministic, uz/ru/en,
   Latin and Cyrillic).
2. **Write**: one model call returns *content only* as JSON (field values and section
   texts in the type's order). Short papers use the economical `chat` route; long ones
   (hisobot, ma'ruza, research proposal) use `reasoning`. Facts may come only from the
   user's message, the organization profile and attached files or the knowledge base,
   which are cited.
3. **Validate** (`writing/service.py`):
   - a field whose value contains a number or date the user never gave is emptied and
     becomes a placeholder, so a draft never carries an invented date or document number;
   - numbers in the text that the user did not give are listed for checking;
   - claims of signing, approval, registration or a seal are flagged;
   - style check (`writing/style.py`, no model): empty openers ("Hozirgi kunda…"),
     inflated praise, repeated phrases, mixed Latin/Cyrillic, overlong sentences;
   - length against the requested range, sections present, script (Latin vs Cyrillic).
4. **Lay out** (`writing/render.py`): A4, margins 30/15/20/20 mm, Times New Roman 14 pt,
   justified text with a 1.25 cm indent. Letterhead from the profile, outgoing number and
   date, recipient block on the right, centred title, signature block with `[imzo]` and
   `[M.O.]` placeholders. Minutes get Rais/Kotib lines; acts and orders get
   number/place/date and a seal place.
5. **Store** as an artifact: DOCX, plus a PDF (LibreOffice when installed, otherwise
   EZO's text PDF), Markdown and plain text. The validation report is in the metadata.

**Drafts are drafts.** Official types carry "QORALAMA" in the page header and "Draft" in
the document properties. The reply says the paper becomes official only after an
authorized person reviews, signs and registers it. EZO never produces signatures, seals,
approval marks or registration numbers.

## Organization profile

Settings → *Tashkilot profili*, or `/api/writing/organizations`. It holds the name,
type, department, address, contacts, the head's position and name, the letterhead lines,
house-style notes and preferred terms (`{"avoid": "use instead"}`). Only what the user
enters is used. The profile is passed to the writer as data, never as instructions. It
can be edited, exported and deleted.

Since Stage E1 it also holds the standard formatting (font, size, spacing, indent,
margins), a logo, approved Word templates (`{{matn}}` marks where the text goes) and
example documents used only as style references. See
[GOVERNMENT_WORK.md](GOVERNMENT_WORK.md).

## Limits (honest)

- The model writes the prose. EZO checks it but cannot guarantee every sentence is
  perfect Uzbek; the style check catches common machine patterns only.
- Names are not verified against anything; a name the model adds is visible in the draft
  for the user to check. Numbers and dates are verified against the request.
- Logos, approved templates and example documents: see
  [GOVERNMENT_WORK.md](GOVERNMENT_WORK.md) (Stage E1).
- Telegram posts and other social media content are planned (Stage G).
