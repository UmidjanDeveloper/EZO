# Troubleshooting

Start with the doctor — it checks the most common problems and says how to fix them:

```bash
python scripts/ezo.py doctor        # Windows: py scripts\ezo.py doctor
```

## EZO says “offline mode”

No AI provider key was found. Open `.env`, add a key after the `=` sign (no spaces, no
quotes), save, and restart EZO (`docker compose up` or `python scripts/ezo.py dev`).
**Settings → System status** shows which providers are connected.

## “None of the AI providers answered”

Open the conversation’s **Iz (debug)** panel: *Provider attempts* shows the reason per provider.

| Reason | Meaning | Fix |
|---|---|---|
| `auth` | The API key was rejected | Copy the key again into `.env`; check it is active |
| `rate_limit` | Too many requests or no credit left | Wait a minute; check billing on the provider’s website |
| `model_not_found` | The model name does not exist for your key | Update the model name in `apps/api/config/models.toml` |
| `unavailable` / `timeout` | Network problem or provider outage | Check your internet; try again later |

## “Cannot reach the EZO API. Is it running?”

The web app cannot talk to the API.

- Docker: run `docker compose ps` — `api` should be `healthy`. If not: `docker compose logs api`.
- Developer mode: the terminal running `ezo.py dev` shows API errors. Check
  <http://localhost:8000/api/health> in the browser.
- If you changed ports or run the API elsewhere, set `EZO_API_URL` (web, runtime) and add the
  web address to `EZO_CORS_ORIGINS` (API).

## “PostgreSQL is not running” / database errors

- Start the database: `docker compose up -d db`, wait 10 seconds, try again.
- Port 5432 already used by another PostgreSQL on your computer: stop that one, or change the
  port mapping in `docker-compose.yml` (e.g. `"127.0.0.1:5433:5432"`) and in `.env`
  (`DATABASE_URL=...localhost:5433/ezo`).
- No Docker at all: use `DATABASE_URL=sqlite:///./ezo.db` in `.env`.

## Port 3000 or 8000 is already in use

Another program uses the port. Close it (often an older EZO window), or find it:

- Windows: `netstat -ano | findstr :3000` then `taskkill /PID <number> /F`
- macOS/Linux: `lsof -i :3000` then `kill <PID>`

## Docker: “error during connect” / “Cannot connect to the Docker daemon”

Docker Desktop is not running. Start it and wait for *Engine running*.

## `python` / `uv` / `pnpm` is not recognized (Windows)

Close and reopen PowerShell after installing a tool. Use `py` instead of `python`. Install
pnpm with `npm install -g pnpm`.

## Voice mode (Gaplashish) does not work

| Symptom | Fix |
|---|---|
| “Bu brauzer ovozni tanimaydi” | Use Chrome, Edge or Safari. Firefox has no speech recognition. |
| “Mikrofonga ruxsat berilmagan” | Click the lock icon in the address bar → allow **Microphone** → reload. |
| “Ovoz eshitilmadi” | Speak right after tapping the robot; check the right microphone is selected in Windows sound settings. |
| “Nutqni tanish xizmatiga ulanib bo‘lmadi” | Browser speech recognition needs internet (Chrome sends audio to its speech service). |
| Replies are read in a strange accent | The device has no voice for that language (common for Uzbek). Windows: Settings → Time & language → Speech → add a voice. |
| EZO hears the wrong language | Pick UZ / EN / RU above the robot. |
| “Server ovozi hozir ishlamayapti…” | The server voice (OpenAI or VoiceStudio) failed. EZO switched to the browser’s voice for this session. Check the key or that VoiceStudio is running (`docker compose --profile voice ps`, `docker compose logs voicestudio`), then reload the page. |
| Settings shows “Using the browser’s voice” although VoiceStudio runs | Set `VOICESTUDIO_URL` in `.env` (Docker: `http://voicestudio:3900`) and restart the API. |
| VoiceStudio is slow the first time | It downloads several GB of models on first start. Wait until `docker compose logs voicestudio` shows it is ready. |

## Files (Fayllar) and sources

| Symptom | Fix |
|---|---|
| “This file type is not supported” | Allowed: PDF, DOCX, XLSX, CSV, TXT, MD, PNG/JPG/GIF/WEBP. Old `.doc`/`.xls`: open in Word/Excel and *Save as* `.docx`/`.xlsx`. |
| “The file is not a real PDF/…” | The file was renamed (e.g. `.exe` → `.pdf`) or is damaged. Export it again from the original program. |
| “The file is too large” (413) | Raise `EZO_MAX_UPLOAD_MB` in `.env` (default 25) and restart, or split the file. |
| Status **Qisman / Partial** | Files are found by keywords only. Add `OPENAI_API_KEY` or `GEMINI_API_KEY` to `.env`, restart, then press **Qayta o‘qish / Re-read** on the file. |
| Status **OCR kerak / Needs OCR** | The file is an image or a scanned PDF without a text layer. Reading text from images arrives in a later phase (ROADMAP Phase 6.5); for now use a PDF with selectable text. |
| Status **Xato / Failed** | The message under the file says why (password-protected, damaged, empty). Fix the file and upload again. |
| A file stays **O‘qilmoqda / Reading** | Large PDFs take a while. If the API restarted, reading resumes automatically. Check `docker compose logs api`. |
| EZO answers without using my file | Ask about the file’s content directly (“shartnomada muddat qancha?”). In casual chat EZO only uses files that clearly match. Files in a project are used only inside that project. |
| “Add link” says the address is not allowed | EZO never fetches private or local addresses (security). Use a public `https://` page. Some sites forbid automated reading in `robots.txt`; EZO respects that. |

## Created (Yaratilganlar) and versions

| Symptom | Fix |
|---|---|
| “Saqlash / Save” is greyed out | That answer is already saved (see the card under it), or it is still being written. |
| An edit did not create a new version | The text was identical to the current version; nothing new is stored. |
| I restored an old version and now have one more version | That is intended: restoring never deletes or rewrites history, it adds the old content again as the newest version. |
| Download says the stored file is missing | The storage folder/volume was deleted or moved (`ezo-storage` in Docker, `apps/api/storage` in developer mode). Restore it from a backup. |
| Deleting a project removed my files? | No — artifacts stay in *Created*; they just no longer belong to a project. |

## Web research says “web search is not configured”

Add `ANTHROPIC_API_KEY` (EZO uses Claude’s web search) or a `TAVILY_API_KEY`
(https://tavily.com) to `.env` and restart. `EZO_WEB_SEARCH_PROVIDER=none` turns web search off.
If searches fail with quota errors, the provider’s plan limit was reached.

## Semantic search was enabled later / embedding model changed

Vectors are stored per embedding model. After adding an OpenAI/Gemini key or changing
`[[embeddings.candidates]]` in `models.toml`, press **Re-read** on your files so they get
vectors for the new model (keyword search keeps working meanwhile).

## “429 Too many requests”

The built-in rate limiter stopped a burst of requests. Wait a minute, or raise
`EZO_RATE_LIMIT_CHAT` / `EZO_RATE_LIMIT_DEFAULT` in `.env`.

## “401 Missing or invalid API token”

`EZO_AUTH_MODE=token` is set. Enter the same value as `EZO_API_TOKEN` in
**Settings → API token** in the web app.

## After `git pull`, things break

Dependencies or the database schema changed:

```bash
python scripts/ezo.py setup
python scripts/ezo.py migrate
```

With Docker: `docker compose up --build` (migrations run automatically).

## Reset everything (deletes all your data)

```bash
docker compose down -v
```

This deletes the database **and** the uploaded files (`ezo-db` and `ezo-storage` volumes).
In developer mode uploaded files are in `apps/api/storage/` (or `EZO_STORAGE_DIR`).

## Getting more detail

- Set `EZO_LOG_LEVEL=DEBUG` in `.env` for verbose API logs.
- Every chat turn is recorded as an *agent run* (routing decisions, steps, provider attempts,
  errors) — visible in the **Iz (debug)** panel and at `GET /api/agent-runs`.

## Documents and presentations

- **“EZO cannot write the presentation content”** — no AI provider is connected. Writing
  documents and slides needs a model. Converting files and comparing them still work offline.
- **“no matching uploaded file was found”** — upload the file first (paperclip), or name it
  (“report.pdf ni …”). Files in another project are not visible from this conversation.
- **The quality check reports problems** — EZO already tried one automatic repair. Ask for a
  concrete change (“5-slaydni qisqartir”); it becomes a new version and the old one is kept.
- **A scanned PDF cannot be read** — OCR is not built in yet; the file shows `needs_ocr`.
- **Fonts look different in PowerPoint** — slides use Arial, which is metric-compatible with
  the Liberation Sans used for fitting. If Arial is missing, the app substitutes a similar font.

## Orchestration / Ruflo

- **“Advanced orchestration provider unavailable; continuing with EZO's native workflow.”**
  This is expected. Ruflo is optional and not active in this version. Nothing is broken, and
  EZO's native workflow is used.
- **I ran `ruflo init` in the EZO folder by mistake.** It writes `.claude/`, `.claude-flow/`,
  `.swarm/`, `CLAUDE.md` and `.mcp.json`, and pre-approves all of its tools. Remove those files
  (check with `git status`) and the “Ruflo Integration” block it appended to
  `~/.claude/CLAUDE.md`.
