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

## Getting more detail

- Set `EZO_LOG_LEVEL=DEBUG` in `.env` for verbose API logs.
- Every chat turn is recorded as an *agent run* (routing decisions, steps, provider attempts,
  errors) — visible in the **Iz (debug)** panel and at `GET /api/agent-runs`.
