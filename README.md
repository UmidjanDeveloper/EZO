# EZO

**EZO — Sen bilan o‘sadigan shaxsiy sun’iy intellekt.**
*A personal AI operating system that grows with you.*

EZO is not a chatbot clone. It is a modular personal AI system that understands what you
need, picks the right specialist agent, remembers what matters, and (milestone by milestone)
learns to research, create documents and presentations, coach languages, write code and run
longer workflows. The interface is Uzbek first, with English and Russian built in.

> **Status: Milestones 1 (Foundation) and 2 (Knowledge, files and research) are complete.**
> The screen shows only the EZO robot and your conversation history. You can type, talk to EZO
> out loud, give it your files, or ask it to research the web — answers come with sources.
> EZO decides by itself which specialist agent a request needs — there are no agent menus.
> See [ROADMAP.md](ROADMAP.md) and [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

---

## Tezkor boshlash (Uzbek quick start)

1. [Docker Desktop](https://www.docker.com/products/docker-desktop/) ni o‘rnating va ishga tushiring.
2. Loyiha papkasida `.env.example` faylidan nusxa olib, nomini `.env` qiling.
   Ichiga kamida bitta AI kalitini yozing (masalan `ANTHROPIC_API_KEY=...`).
3. Terminalda (Windows: PowerShell) loyiha papkasida:

   ```
   docker compose up --build
   ```

4. Brauzerda oching: **http://localhost:3000**
5. Fayl berish: xabar oynasi yonidagi 📎 tugmasi yoki pastdagi **Fayllar** belgisi.
   Internetdan izlash uchun: “internetdan qidir: …” deb yozing (Anthropic yoki Tavily kaliti kerak).

To‘xtatish: terminalda `Ctrl+C`, keyin `docker compose down`.
Windows uchun batafsil qo‘llanma: [SETUP_WINDOWS.md](SETUP_WINDOWS.md).

---

## Quick start with Docker (recommended)

You only need **Docker Desktop**. Nothing else has to be installed.

```bash
# 1. Create your configuration file (Windows PowerShell: copy .env.example .env)
cp .env.example .env

# 2. Open .env in a text editor and add at least one AI key, e.g.
#    ANTHROPIC_API_KEY=sk-ant-...
#    (Without a key EZO starts in "offline mode" and tells you how to connect one.)

# 3. Start everything: database + API + web app
docker compose up --build
```

Open **http://localhost:3000**. The API and its interactive documentation are at
**http://localhost:8000/docs**.

| Task | Command |
|---|---|
| Start (after the first time) | `docker compose up` |
| Start in the background | `docker compose up -d` |
| Stop | `docker compose down` |
| See logs | `docker compose logs -f api` |
| Update after pulling new code | `docker compose up --build` |
| Delete all data (careful!) | `docker compose down -v` |

Your data lives in the Docker volume `ezo-db` and survives restarts.

## Developer mode (hot reload)

For changing the code. Install **Python 3.12+**, **[uv](https://docs.astral.sh/uv/)**,
**Node.js 20.9+** with **pnpm**, and **Docker** (for the database). Then:

```bash
python scripts/ezo.py doctor   # checks that everything is installed
python scripts/ezo.py setup    # installs dependencies, creates .env
python scripts/ezo.py dev      # starts database + API + web; Ctrl+C stops
```

On Windows use `py scripts\ezo.py ...` if `python` is not found.

| Command | What it does |
|---|---|
| `python scripts/ezo.py doctor` | Checks your computer and explains what is missing |
| `python scripts/ezo.py setup` | Creates `.env`, installs Python and JavaScript dependencies |
| `python scripts/ezo.py dev` | Starts PostgreSQL (Docker), migrates, runs API (`:8000`) and web (`:3000`) |
| `python scripts/ezo.py migrate` | Applies database migrations |
| `python scripts/ezo.py test` | Lint + type-check + all unit/integration tests |
| `python scripts/ezo.py test --e2e` | …plus browser end-to-end tests |
| `python scripts/ezo.py build` | Production builds (`--docker` also builds images) |

**No Docker?** Put `DATABASE_URL=sqlite:///./ezo.db` in `.env` to use a simple file database
(good for trying EZO; PostgreSQL is the real target).

## Connecting AI providers

Add one or more keys to `.env` and restart:

| Provider | Variable | Get a key |
|---|---|---|
| Anthropic Claude | `ANTHROPIC_API_KEY` | https://console.anthropic.com/settings/keys |
| OpenAI | `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| Google Gemini | `GEMINI_API_KEY` | https://aistudio.google.com/apikey |

EZO routes each kind of work to a suitable model (fast model for chat, strongest model for
reasoning and code…) and falls back to the next provider if one fails. Routes and model names
are in [`apps/api/config/models.toml`](apps/api/config/models.toml). Set
`EZO_PREFERRED_PROVIDER` to put one provider first. **Settings → System status** in the app
shows which providers are connected and which model each route uses.

## What works today (Milestones 1–2)

- **Minimal interface:** the EZO robot inside a calm orb in the centre, the conversation
  history on the left (Files, Memory, Projects and Settings are small icons at the bottom).
  The orb shows what EZO is really doing — idle, listening, thinking, speaking, searching,
  reading sources, working, done or error — and a small status appears in the header while
  EZO is busy. Stages come from the server (a tool really started), never invented.
- **Two ways to talk, one conversation:** **Yozish** (type) with streaming replies, Markdown
  and a stop button, or **Gaplashish** (talk): tap the robot, speak, and EZO answers out loud,
  then listens again — hands-free, like talking to a person. Tap while it speaks to interrupt.
  Voice replies are short and conversational (EZO is told it is being heard, not read).
  Any reply can also be read aloud with the speaker button.
- **EzoCore pipeline:** language detection (uz/en/ru) → intent classification → agent
  selection → context → memory retrieval → plan → prompt → model routing with fallback →
  quality checks → saving → memory capture. Every step is traced.
- **Automatic agent routing (behind the scenes):** “English speaking qilamiz”, “15 slide
  presentation tayyorla”, “GitHub bugini top”, “prezident qarorini tushuntir” are recognised
  and routed without any menus. Agents that are not built yet are covered by the General
  Companion, which is told exactly what it cannot do (it will not invent law numbers or claim
  it created a file).
- **Memory:** EZO stores only meaningful statements (explicit “eslab qol…”, preferences,
  goals, personal facts, learning difficulties, decisions) with importance scoring, never
  stores passwords/cards/passports automatically, and lets you view, add and delete memories.
- **Projects** with their own conversations and project memory.
- **Personality engine** (`apps/api/config/personality.toml`): calm, honest, not sycophantic;
  style adapts to context (casual, professional, technical, teacher).
- **Providers:** Anthropic, OpenAI and Gemini adapters behind one interface, plus an offline
  mode that works with no keys.
- **Security basics:** auth abstraction (local owner or token mode), rate limiting, input
  limits, parameterized queries (SQLAlchemy), audit log for deletions and memory changes,
  security headers, no secrets in code.
- **Debug traces:** turn on *Debug* in Settings, then click **Iz (debug)** under a reply to
  see routing, steps, provider attempts, latency and tokens. Hidden model reasoning is never
  stored.
- **UI:** dark and light themes, mobile layout, Uzbek / English / Russian interface.
- **Files and knowledge (Milestone 2):** see the next section.

## Files, knowledge and research (Milestone 2)

- **Give EZO your files:** click the paperclip next to the message box, or open **Files**
  (bottom-left icon) and drop files there. Supported: PDF, Word (DOCX), Excel (XLSX), CSV,
  TXT, Markdown, and web pages by link. Images are accepted and stored, but reading text in
  images (OCR) arrives with Milestone 4 — EZO says so instead of pretending.
- **Answers with sources:** when your question is about your files, EZO searches them and
  answers with numbered citations like `[1]`. Under the answer you see the sources (file,
  page, version). Citation numbers that do not match a real source are removed automatically,
  so EZO cannot invent a source.
- **Versions, not overwrites:** upload a changed file with the same name and EZO keeps the
  old version and searches only the new one. Identical files are detected as duplicates.
- **Web research:** say “internetdan qidir…”, “search the web…”, “найди в интернете…” or ask
  for the latest news. EZO plans search queries, searches, prefers official/primary sources,
  reads the best pages and answers with dated, cited facts. Needs an Anthropic key (Claude web
  search) or a `TAVILY_API_KEY`; without either EZO tells you web search is not configured.
- **Smarter memory:** with an OpenAI or Gemini key, memories are found by meaning (not just
  matching words), mixed with importance, recency and project relevance.
- **Search modes:** meaning-based (“semantic”) search needs an OpenAI or Gemini key for
  embeddings; without one, files are still found by keywords. On PostgreSQL EZO uses the
  pgvector extension automatically; otherwise a built-in vector store.

| Setting (`.env`) | What it does | Default |
|---|---|---|
| `TAVILY_API_KEY` | Web search through Tavily | empty |
| `EZO_WEB_SEARCH_PROVIDER` | `auto`, `anthropic`, `tavily` or `none` | `auto` |
| `EZO_MAX_UPLOAD_MB` | Largest upload | `25` |
| `EZO_STORAGE_DIR` | Where uploaded files are kept | `apps/api/storage` (Docker: volume `ezo-storage`) |
| `EZO_VECTOR_STORE` | `auto`, `pgvector` or `local` | `auto` |
| `EZO_INGESTION_MODE` | `background` (don’t wait) or `inline` | `background` |

### Voice mode notes

Voice works in three ways, and EZO picks the best one automatically:

| Engine | Needs | Notes |
|---|---|---|
| **Browser voice** (default) | Chrome, Edge or Safari | Built into the browser. Firefox cannot recognise speech. Uzbek voices depend on the device. In Chrome/Edge the browser maker’s online service hears your audio. |
| **OpenAI voice** | `OPENAI_API_KEY` | EZO records your sentence, OpenAI transcribes it and reads replies aloud (natural voice, good Uzbek/English/Russian). |
| **VoiceStudio** (optional, local) | the `voice` Docker profile | Runs on your own computer. See *Optional integrations* below. |

When a server voice is configured, EZO records until you pause, sends the recording to the
API, and the API transcribes it and forgets the audio. Only the text becomes part of the chat.
EZO never stores your voice recordings. If the server voice fails, EZO tells you and continues
with the browser’s voice; if reading a reply aloud fails, the browser reads it instead. Tap the
robot while EZO speaks to interrupt it and talk. Choose the speech language (UZ / EN / RU) above
the robot; **Settings → System status → Voice** shows which engine is active. Fully realtime,
streaming voice (talk over each other, word-by-word) is planned for Milestone 7.

## Created files and versions (Yaratilganlar)

Everything EZO makes — and every answer you choose to keep — becomes an **artifact**: a file
you can come back to later.

- **Save an answer:** press **Saqlash / Save** under any EZO answer. It is stored as a
  Markdown document, keeps the answer’s sources, and appears as a card under the answer.
- **Yaratilganlar / Created** (layers icon, bottom-left) lists everything with type, project,
  date and version. Open an item to preview, **edit** (text files), **download**, **rename** or
  **delete** it.
- **Versions are never overwritten.** Each edit becomes a new version (v2, v3…); older versions
  stay downloadable. “Restore this version” makes an old version current by adding it again as
  a new version — history is never rewritten. Deleting an artifact (with confirmation) is the
  only way to remove versions.
- Files are stored in the same safe storage as uploads (Docker volume `ezo-storage`), are only
  visible to you, and are always downloaded as files (never opened as web pages).
- Behind the scenes EZO also has **story projects** (scenes, narration, timing): every
  presentation keeps one, so it can later become a video.

## Documents and presentations (Hujjat va taqdimotlar)

Just ask in chat — EZO picks the right specialist itself:

| Try | What happens |
|---|---|
| “AI haqida 10 slaydli taqdimot tayyorla” | A real **PPTX** (editable text, native charts and tables, speaker notes) plus **PDF**, a **web version** and slide previews |
| “Shu PDF asosida taqdimot tayyorla” (after uploading) | The deck is built from your file and ends with a *Manbalar / Sources* slide |
| “3-slaydni qisqartir” | The same presentation gets **version 2**; version 1 is kept |
| “Hokimga rasmiy ariza yozib ber” | A **DOCX** (+ PDF, Markdown) with placeholders like `[F.I.Sh.]` for details you did not give |
| “Shu faylni ingliz tiliga tarjima qil” | A new translated document with a change summary; your upload is never changed |
| “Bu ikki hujjatni solishtir” | A paragraph-level comparison (works offline) |
| “Shu excel jadvalni tahlil qil” | Exact column statistics computed by EZO, explained in plain words |
| “Oylik xarajatlar uchun excel jadval yarat” | An **XLSX** (+ CSV); unknown values stay empty, never invented |
| “Shu faylni PDF ga aylantir” | Format conversion — works even without an AI key |

Every presentation goes through a layout check (text that does not fit, tiny fonts, elements
outside the slide, broken chart data…). EZO repairs problems once automatically and tells you
honestly if anything remains. Images are abstract visuals for now (image generation arrives
with the Visual Agent). Scanned PDFs need OCR, which is not built in yet.

## Optional integrations

None of these is needed for normal EZO chat. Each one is off until you turn it on, and EZO
keeps working if it is missing or broken. Licence details:
[docs/OPEN_SOURCE_AUDIT.md](docs/OPEN_SOURCE_AUDIT.md).

### VoiceStudio — local voice (speech-to-text and text-to-speech)

- **What it does:** turns your speech into text and reads EZO’s replies aloud, on your own
  computer, through VoiceStudio’s OpenAI-compatible API.
- **Required?** No. Without it, EZO uses OpenAI voice (if `OPENAI_API_KEY` is set) or the
  browser’s voice.
- **Licence:** VoiceStudio is AGPL-3.0 and runs as a separate container; no VoiceStudio code is
  inside EZO. **Its default voice model is licensed for non-commercial use only.**
- **Install:**
  1. In `.env`:
     ```
     VOICESTUDIO_URL=http://voicestudio:3900
     VOICESTUDIO_API_KEY=any-long-random-text
     ```
  2. Run `docker compose --profile voice up --build`. The first start downloads several GB
     of models, which can take a while. VoiceStudio is not published on your network; only
     the EZO API can reach it.
- **Test:** open **Settings** and check that *Voice* says “Server voice: voicestudio”. Then
  open **Gaplashish**, tap the robot and speak.
- **Disable:** clear `VOICESTUDIO_URL` in `.env` and start without `--profile voice`.

### Ruflo — multi-agent orchestration (prepared, not active)

- **What it is:** an MIT-licensed tool that coordinates many AI agents. EZO may later use it,
  as an *optional* helper, for very large jobs such as “repo’ni audit qil va fix qil”.
- **Required?** No. EZO has its own native mission runner, and nothing needs Ruflo. It is
  **off by default** (`EZO_ORCHESTRATION_PROVIDER=native`, `EZO_RUFLO_ENABLED=false`).
- **Status:** audited and planned, not active. Even with it enabled, EZO currently uses its
  native workflow and says so: *“Advanced orchestration provider unavailable; continuing with
  EZO's native workflow.”*
- **Security warning:** Ruflo can run shell commands, merge on GitHub, and update itself. EZO
  will only talk to it through a strict allow-list, with no API keys and in an isolated
  directory. **Do not run `ruflo init` inside the EZO folder.** See
  [docs/RUFLO_INTEGRATION_PLAN.md](docs/RUFLO_INTEGRATION_PLAN.md) and the audit in
  [docs/OPEN_SOURCE_AUDIT.md](docs/OPEN_SOURCE_AUDIT.md).
- **Developer mode (without Docker):** run VoiceStudio yourself (it listens on
  `http://localhost:3900`) and set `VOICESTUDIO_URL=http://localhost:3900`.

### OpenMontage — video production (planned, Phase 4)

Not integrated yet. It will be an optional `studio` Docker profile that renders videos from
EZO’s presentation/story projects. It is AGPL-3.0 and will run as a separate service.

### REA — binary analysis (planned, Phase 6)

Not integrated. It will only be offered to the DeveloperAgent, off by default, and only for
software you own or are allowed to analyse.

## Repository layout

```
apps/
  api/            FastAPI backend (Python): EzoCore, agents, providers, memory, DB
    config/       models.toml (routing), personality.toml
    migrations/   Alembic database migrations
    src/ezo_api/  application code
    tests/        unit + integration tests
  web/            Next.js web app (React, Tailwind CSS, Framer Motion)
packages/
  shared/         TypeScript API types + client (streaming SSE parser, uploads)
  ui/             shared React components
tests/e2e/        Playwright browser tests
scripts/ezo.py    setup / dev / test / build helper
docker-compose.yml
```

More: [ARCHITECTURE.md](ARCHITECTURE.md) · [ROADMAP.md](ROADMAP.md) ·
[TROUBLESHOOTING.md](TROUBLESHOOTING.md) · [SETUP_WINDOWS.md](SETUP_WINDOWS.md) ·
[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) · [Open-source audit](docs/OPEN_SOURCE_AUDIT.md) ·
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)

## Testing

```bash
python scripts/ezo.py test          # everything except browser tests
python scripts/ezo.py test --e2e    # including Playwright browser tests
```

Backend tests run on SQLite by default; set `EZO_TEST_DATABASE_URL` to a PostgreSQL URL to
run the same tests on PostgreSQL. CI (`.github/workflows/ci.yml`) runs both.

## Security notes

- Keep `.env` private. It is in `.gitignore`; never commit it.
- `EZO_AUTH_MODE=local` means *no login* and is meant for your own computer only. If EZO can be
  reached by other people (a server, your home network), set `EZO_AUTH_MODE=token` and a long
  random `EZO_API_TOKEN`, and enter that token in **Settings**.
- Docker publishes ports only on `127.0.0.1` (your computer), not on the network.
- Uploads are checked by content, not only by name (a renamed `.exe` is rejected), limited in
  size, stored under random-safe names, and never served back as web pages.
- “Add link” and EZO’s web reading refuse private/internal addresses (SSRF protection) and
  respect `robots.txt`. Text from files and web pages is treated as data: instructions inside
  them are ignored.
- Every tool EZO uses (file search, web search, page reading) is logged with redacted
  arguments; see the debug trace of an answer.
