# EZO

**EZO — Sen bilan o‘sadigan shaxsiy sun’iy intellekt.**
*A personal AI operating system that grows with you.*

EZO is not a chatbot clone. It is a modular personal AI system that understands what you
need, picks the right specialist agent, remembers what matters, and (milestone by milestone)
learns to research, create documents and presentations, coach languages, write code and run
longer workflows. The interface is Uzbek first, with English and Russian built in.

> **Status: Milestone 1 (Foundation) is complete.** Chat, conversations, projects, memory,
> provider routing with fallback, and the EzoCore pipeline work end to end. Specialist agents
> (language coach, presentations, research…) are shown in the app as *coming soon* with the
> milestone that delivers them. See [ROADMAP.md](ROADMAP.md).

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

## What works today (Milestone 1)

- **Chat** with streaming replies, Markdown, stop button, conversation history.
- **EzoCore pipeline:** language detection (uz/en/ru) → intent classification → agent
  selection → context → memory retrieval → plan → prompt → model routing with fallback →
  quality checks → saving → memory capture. Every step is traced.
- **Agent routing:** “English speaking qilamiz”, “15 slide presentation tayyorla”,
  “GitHub bugini top”, “prezident qarorini tushuntir” are recognised. Agents that are not
  built yet are clearly marked; the General Companion helps meanwhile and is told exactly what
  it cannot do (e.g. it will not invent law numbers or claim it created a file).
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
- **Debug traces:** click **Iz (debug)** in a chat to see routing, steps, provider attempts,
  latency and tokens. Hidden model reasoning is never stored.
- **UI:** dark and light themes, mobile layout, Uzbek / English / Russian interface.

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
  shared/         TypeScript API types + client (streaming SSE parser)
  ui/             shared React components
tests/e2e/        Playwright browser tests
scripts/ezo.py    setup / dev / test / build helper
docker-compose.yml
```

More: [ARCHITECTURE.md](ARCHITECTURE.md) · [ROADMAP.md](ROADMAP.md) ·
[TROUBLESHOOTING.md](TROUBLESHOOTING.md) · [SETUP_WINDOWS.md](SETUP_WINDOWS.md)

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
