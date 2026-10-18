# Translation

EZO translates between **Uzbek (Latin)**, **Uzbek (Cyrillic)**, **Russian** and
**English**. It also converts Uzbek between Latin and Cyrillic, keeps your terminology,
and checks every translation against its source. Status: **alpha**.

## Ask in chat

| Try | Result |
| --- | --- |
| "Inglizchaga tarjima qil: …" (text after a colon or on the next line) | The translation in the reply, then EZO's check results |
| Attach a Word file: "Shu ruscha hujjatni o'zbek lotiniga tarjima qil, formatini saqla" | A new Word file translated **in place**: styles, bold/italic, tables, lists, images, headers/footers and links kept |
| "… o'zbek kirilliga tarjima qil, ikki tilli variantini ham ber" | Uzbek Cyrillic, plus a two-column **bilingual** Word file as an extra download |
| Attach a PDF or text file: "Inglizchaga tarjima qil" | A translated Word document (the text is kept; the PDF's page layout is not) |
| "Kirillga o'gir: …", attach a file and say "Shu faylni lotin yozuviga o'tkaz" | Script conversion — **no AI model, works offline**; Word files keep their formatting |
| "Glossariyga qo'sh (inglizcha): «hokimlik» → «khokimiyat»" | Saves a term pair; EZO uses it and checks it was used |
| "rasmiy / ilmiy / texnik / huquqiy / biznes" in the request | Style: official correspondence, academic, technical, legal (faithful), business |

The **Translation** page (`/translate`) has the same text translation, the Latin ↔ Cyrillic
buttons, the check results and the glossary editor.

## How a translation is made

1. **Languages.** The target comes from the request: a name marked as the target wins
   ("o'zbek lotiniga", "into", "на"), otherwise the last one named. The source is the one
   marked "-dan / from / с", otherwise it is detected from the text. With no target named,
   EZO translates into your language (or English for Uzbek text).
2. **Script changes need no model.** Uzbek Latin → Uzbek Cyrillic (and back) is done by
   `translation/translit.py` with fixed rules. Into Uzbek Cyrillic from another language,
   the model writes Uzbek (Latin) and EZO converts the script, so the Cyrillic always
   follows one rule set.
3. **Glossary.** Your terms for this language pair are matched in the text (word endings
   and either Uzbek script are tolerated: "hokimlik" also matches "ҳокимлигига"). Only the
   matching terms go to the model, as required translations. Terms of your default
   organization come before general ones; other organizations' terms are not used.
4. **Translate.**
   - Text: paragraph batches of about 6,000 characters through the economical `chat`
     route. The model also lists ambiguous places it had to decide.
   - Word files: the existing DOCX-fidelity editor (`agents/docx_office.py`). Only
     paragraph texts with formatting markers go to the model, and every paragraph is
     required (missing ones are retried once, then reported).
   - Other files go through Markdown; files over 40,000 characters are translated part by
     part with the resumable long-document cache.
5. **Check** (`translation/quality.py`, no model). Each finding is reported to you;
   nothing is silently "fixed":
   - **numbers**: the same values on both sides ("1 250 000" = "1,250,000", "3,5" = "3.5").
     A month name next to a number counts as that month, so "12-mart", "March 12" and
     "12 марта" agree ("3 marta" means "three times" and is not a month);
   - **links and e-mail addresses** unchanged;
   - **names**: surnames (-ov, -ev, -ova, -yeva, -ovich, -skiy…) still present, in any
     script or common romanisation (Каримов = Karimov, Xo'jayev ≈ Khodjaev);
   - **glossary**: each required term used;
   - **paragraphs**: none empty, none left in the source language, no suspicious length
     change; for Word files the check is paragraph by paragraph;
   - **script** of Uzbek output; **ambiguities** listed by the translator, `[?]` marks.
6. **Store** as an artifact with the check report in its metadata
   (`translation_quality`). The original upload is never changed.

## Latin ↔ Cyrillic rules

- е → **ye** at the start of a word and after a vowel (Ер → Yer, поезд → poyezd), else **e**;
  Latin **e** → э at the start of a word and after a vowel (ekologiya → экология).
- ё/ю/я ↔ yo/yu/ya, but **yo'l** stays й + ў (йўл); ў/ғ ↔ o'/g'; ш/ч ↔ sh/ch; ҳ ↔ h; қ ↔ q.
- **ъ** ↔ tutuq belgisi (маъно ↔ ma'no); "s'h" separates s and h (Исҳоқ ↔ Is'hoq).
- **ц** → s at the start / after a consonant, ts after a vowel (цирк → sirk, лицей →
  litsey). Back to Cyrillic, ц comes from -tsiya, -ksiya, -nsiya and a short list of common
  loanwords (sotsial, litsey, prinsip, konsert, sentr, sement, sirk…). The soft sign is
  added to month names (sentabr → сентябрь).
- Apostrophes: ' ‘ ’ ʻ ʼ ` are all understood; Latin output uses ' by default, or the
  official modifier letters (oʻ, ʼ) with `apostrophe: "modifier"` in the API.
- Links, e-mail addresses and digits are never changed. Word files are converted run by
  run, so a letter pair split across two formatting runs ("S|hahar") still becomes "Ш|аҳар".

Known limits: foreign words and rare loanwords may need proofreading (the ц list is
short), and a Russian text typed in Cyrillic would be letter-converted too — use
translation for Russian.

## Voice interpretation (turn-based)

`POST /api/translation/interpret` (multipart: `audio`, `target`, optional `source`,
`speak`): EZO transcribes one recording, translates it and, if a speech provider is
configured, reads the translation aloud (base64 MP3 in the reply). In a conversation, give
both languages (`source` = one side, `target` = the other): whichever side speaks is
translated into the other language. It needs a speech provider (OpenAI key or
VoiceStudio) and an AI model. Audio is kept in memory only.

This is **turn-based**, not simultaneous interpretation. `StreamingInterpreter` in
`translation/interpreter.py` is the interface for low-latency streaming with interruption,
to be implemented with realtime voice (Phase 8). There is no UI for interpretation yet.

## API

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/translation/languages` | languages, styles, limits |
| POST | `/api/translation/translate` | `{text, target, source?, domain?, use_glossary?, organization_id?}` → text, check report, warnings, terms used; up to 60,000 characters; 503 `offline` without an AI provider (an Uzbek script change still works) |
| POST | `/api/translation/transliterate` | `{text, to: latin|cyrillic, apostrophe?}` — no model |
| GET / POST | `/api/translation/glossary` | list (filter by languages) / add (`source_language`, `target_language` ∈ uz, ru, en; optional `organization_id`, `note`) |
| PUT / DELETE | `/api/translation/glossary/{id}` | owner only (404 otherwise); deleting an organization deletes its terms |
| POST | `/api/translation/interpret` | turn-based voice interpretation (above) |

## API keys

- **No key needed:** Latin ↔ Cyrillic (text and Word files), the glossary, the checks.
- **AI key needed:** translation itself (any of Anthropic, OpenAI, Gemini; route `chat`).
  Without one, EZO says so and translates nothing.
- **Voice interpretation:** additionally a speech provider (OpenAI key or VoiceStudio).

## Privacy

Text and documents you translate are sent to the configured AI provider, like any other
EZO request. Do not translate confidential government or personal documents with an
external provider unless your organization allows it. The Latin ↔ Cyrillic conversion runs
locally and sends nothing anywhere.
