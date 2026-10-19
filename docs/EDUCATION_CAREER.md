# Education, academic research and career

Status: **alpha**. All of it runs through the normal chat and the existing Document and
Presentation engines. Files are saved as artifacts with EZO's check results in their
metadata.

## Teachers and students

| Try | Result |
| --- | --- |
| "7-sinf uchun fotosintez mavzusida 45 daqiqalik dars ishlanmasi tayyorla" | **Lesson package**: Word (+ PDF) with objectives, timed stages, lecture notes, exercises, quiz, homework, rubric and answer key; Excel (questions with key, timing, rubric); a **presentation** |
| Attach lecture notes: "Shu ma'ruzadan 10 ta test tuz" | **Quiz** built from the file: Word with an answer key at the end, Excel with questions and key |
| "Iqtisodiyot fanidan 15 haftalik sillabus tuz" | **Syllabus**: weekly topics, activities, reading, assessment weights |
| "Esse uchun baholash mezonlarini tuz" | **Rubric** with levels and points |
| "IELTSga 6 haftalik tayyorgarlik rejasini tuz" | **Study plan** with sessions and minutes per week |
| Attach the thesis: "Himoya savollarini tuz" | **Defense preparation**: likely questions with answer outlines from your text |
| "… shablonini ber", or no AI key | The same files as a **template** with placeholders (no model, no cost) |

Options are read from the request: number of questions ("10 ta savol"), length ("45
daqiqa", "2 para" = 160 minutes), weeks, level ("7-sinf", "1-kurs", "B1"), slides
("taqdimot bilan"), language and script ("kirillda", "ruscha").

**What EZO checks itself** (reported, never silently changed):
- quiz: each question has 2–6 options and one valid correct answer; the answer key is
  built by EZO, not taken from the model; the number of questions is compared with the
  request;
- lesson: the stages' minutes add up to the lesson length;
- syllabus: assessment weights add up to 100 %, weeks are numbered without gaps;
- rubric: levels ordered by points, maximum computed by EZO;
- study plan: minutes per week computed by EZO.

References are never invented: books or articles appear only when they are in your files;
otherwise the file lists the **kind** of source still needed.

## Academic research

| Try | Result |
| --- | --- |
| "Raqamli hukumat bo'yicha ilmiy manbalarni top, tadqiqot rejasini tuz va himoyaga tayyorlanishimga yordam ber" | Research plan (questions, objectives, hypotheses, methodology, literature review, timeline, defense questions) + reference list + Excel literature matrix |
| "Find research papers on e-government adoption, IEEE style" | Literature list only (works **without an AI key**) |
| "Shu adabiyotlarni APA formatiga o'tkaz: …" (or attach the list) | Formatted references; unreadable or unverifiable values reported |

How it stays honest:
1. **Search**: OpenAlex (openalex.org), a free open index of research works. EZO keeps
   each work's real authors, year, journal, volume, pages, DOI, citation count and
   abstract. Your attached files are added as sources.
2. **Plan**: the model sees only the numbered works and may cite them only as [n]. EZO
   removes citations to numbers that do not exist and flags sentences that state results
   (a plan cannot have results yet: write them as hypotheses).
3. **References**: written by EZO from the metadata in the chosen style (APA 7 by default;
   MLA 9, Chicago author-date, Harvard, IEEE, GOST 7.0.5-style). Missing details stay
   missing (n.d., s.a.) and are listed in the workbook.
4. **Formatting your own list**: the model only splits each reference into fields; any
   value that does not appear in your text (an author, a year, a DOI) is dropped and
   reported, then EZO formats the rest.

EZO found the works by search and did not read their full texts: read them before citing.
The plan supports your own work; it is not finished research.

## Career

Fill **Settings → Karyera profili** once: contacts, summary, experience with your own
achievements, education, skills, languages, certificates (one entry per line, fields
separated by "|").

| Try | Result |
| --- | --- |
| "Menga CV tayyorla" | CV (Word + PDF) built **exactly** from the profile, no model (headings in the requested language; entries as you wrote them) |
| "Bankdagi data analyst lavozimi uchun cover letter yoz" / "motivatsion xat" | Letter that uses the profile as its only facts; numbers not in the profile or the message are flagged |
| "Data analyst lavozimiga intervyu savollarini tayyorla" | Likely questions with answer outlines from the profile |
| "Job interview qilamiz" | Spoken interview practice with the Language Coach (existing) |

## API

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/academic/styles` | citation styles |
| POST | `/api/academic/cite` | `{style, references: [{title, authors, year, kind, container, volume, issue, pages, publisher, place, url, doi, accessed}]}` → formatted entries and missing fields (no model) |
| GET | `/api/academic/search?q=&limit=&from_year=` | OpenAlex works with an APA line each; 503 when search is off |
| GET / PUT / DELETE | `/api/career/profile` | the user's career profile (one per user) |

## Configuration and keys

- `EZO_SCHOLAR_PROVIDER=openalex` (default) or `none`; `EZO_OPENALEX_MAILTO` optional
  (OpenAlex's "polite pool"). OpenAlex needs no key. Requests go through EZO's SSRF-safe
  fetcher (JSON only, size-limited). Live access to OpenAlex was not verified from the
  development sandbox (its network policy blocks it); tests use a fake search.
- **No key needed:** templates, quiz/lesson checks, the CV from the profile, literature
  search, `/api/academic/cite`.
- **AI key needed:** lesson/quiz/syllabus content, research plans, application letters,
  interview and defense questions, splitting a pasted reference list.

## Limits

- Content quality depends on the model; a teacher or student must review it.
- No grade book or learning platform integration; quizzes are files, not online tests.
- PPTX only for lesson packages (or when slides are asked for); defense slides go through
  the Presentation Agent as before.
- The CV does not translate the profile's entries; write them in the language you need.
- OpenAlex coverage of Uzbek-language journals is limited; add your own sources as files.
