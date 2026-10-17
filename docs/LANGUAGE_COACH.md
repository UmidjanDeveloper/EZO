# Language Coach (Phase 5) — alpha

EZO's Language Coach turns practice into real **sessions** with recorded turns, measured
numbers, an assessment, recurring-mistake tracking and progress over time. There is no
separate app: just talk to EZO.

## Try it

| Say or type | What happens |
|---|---|
| “English speaking qilamiz” | A free-conversation session starts in English |
| “IELTS speaking qilamiz, B2 darajada” | IELTS-style speaking simulator: Part 1 → Part 2 (task card) → Part 3, then automatic feedback |
| “Job interview practice please” / “sayohat”, “grammatika”, “business English”, “debate” | The matching mode |
| *any answer in English* | Stays with the coach while the session is active |
| “Feedback ber” / “Tugatdim” / “Finish” | The session is assessed now |
| “Grammarim yaxshilandimi?” / “Eng ko'p qiladigan 5 ta xatom nima?” / “Oxirgi 10 ta sessionimni tahlil qil” | Progress from stored results |
| “Maqsadim IELTS 7” / “My goal is C1” | The goal is saved and used for the level |

Voice works the same way (**Gaplashish**). With server voice, each spoken turn also carries its
**measured speaking time**, which gives real words-per-minute numbers.

The **Til mashg'ulotlari** page (graduation-cap icon) shows the goal, trends, recurring mistakes,
sessions with estimated bands, the vocabulary list and links to each report. Any session can be
deleted, together with its transcript, results and mistakes.

## Honesty rules (enforced in code, covered by tests)

- EZO is an **IELTS-style examiner simulator**, never an "official IELTS examiner". Every band is
  an **estimated band**, and the report says so.
- Bands are estimated only when there is enough speech: at least **40 learner words**.
  Otherwise no band is given, and EZO says why.
- The range is honest. It covers the half-band rounding of the criteria mean, and it is wider
  for short samples (under 150 words).
- **Pronunciation** cannot be judged from text. In a typed session it is *not assessed*. In a
  spoken session the model may give a cautious *transcript-assisted* estimate. That estimate
  is labelled as such and **never counted in the overall range**. Real acoustic analysis is an
  open interface (`PronunciationConfidence = "acoustic"`) planned with realtime voice (Phase 7).
- A "mistake" is stored only if the learner actually said its quoted text. Invented mistakes
  are dropped and counted. Unknown categories become `other`.
- Measured numbers are computed exactly from the transcript, not by a model: words, lexical
  diversity (moving-window type/token ratio), fillers per 100 words, repeated words, and
  words per minute. Words per minute appears only when every learner turn was timed.
- No AI provider: practice and band estimates are refused with a clear message, and nothing is
  faked or stored.

## Coaching style

- During practice EZO answers naturally and keeps the conversation going. It corrects only
  when a mistake blocks meaning. Mistakes are collected and discussed after the section or
  session.
- Level adaptation: CEFR A1–C2 from the request ("B1 darajada"), the active goal, or nothing.
- Recurring weak points from earlier sessions (e.g. verb tenses) are practised **quietly**: EZO
  asks questions that need those structures and does not mention the weakness.
- Practice replies use the cheap `chat` route. The assessment (once per session) uses the
  `reasoning` route.

## IELTS-style structure

- **Part 1:** five questions on two familiar topics.
- **Part 2:** a task card, with about one minute to prepare and one to two minutes to speak,
  then one rounding-off question.
- **Part 3:** four discussion questions linked to the card.

All questions and task cards in `apps/api/src/ezo_api/language/ielts.py` were **written for
EZO**. They are not copied from published tests. The structure follows the publicly described
format of the IELTS Speaking test.

## Knowledge base: legal sources only

EZO does not bundle copyrighted test books or descriptor texts. The assessment uses EZO's own
short description of the four criteria. To make it reference official material:

1. Download publicly available official material yourself, for example the IELTS Speaking band
   descriptors from the official IELTS website, or British Council public learning pages.
2. Upload it on the **Files** page (or with the paperclip).
3. When a session is assessed, EZO searches your files for "IELTS speaking band descriptors" and
   gives the relevant passages to the assessor as reference material.

Do **not** upload pirated books or paid test banks.

## What is stored

| Table | Content |
|---|---|
| `language_sessions` | mode, CEFR target, status, IELTS part, start/end, measured speaking time, words, estimated band range and criteria, pronunciation confidence, feedback, report artifact |
| `language_turns` | each learner and coach turn (text, channel, IELTS part, word count, measured seconds) |
| `language_metrics` | computed numbers and estimated criteria, each with method and confidence |
| `language_mistakes` | category, exact original, correction, explanation, severity |
| `language_goals` | one active goal (older goals are kept as `replaced`) |
| `language_vocabulary` | suggested words with meaning and example |

Raw audio is never stored. Reports are normal versioned artifacts (DOCX with PDF and Markdown
exports).

## API

`GET /api/language/sessions`, `GET /api/language/sessions/{id}`,
`DELETE /api/language/sessions/{id}?confirm=true`, `GET /api/language/progress`,
`POST /api/language/goals`, `GET /api/language/vocabulary`. Practice itself goes through
`POST /api/chat/stream`. Voice messages may send `speech_seconds`.

## Known limitations

- English is the only practised language for now (the data model has a `language` field).
- Mode, command and level detection is rule-based (uz/en/ru phrases). Unusual phrasing may
  start a free conversation instead of the intended mode.
- The Part 2 preparation minute is not timed by the app.
- Pronunciation is transcript-assisted at best until realtime/acoustic analysis (Phase 7).
- Bands come from a language model checked by rules. They are practice estimates, not
  calibrated against real exam results.
