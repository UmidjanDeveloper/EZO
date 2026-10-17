# EZO on Windows — step by step

This guide assumes you have never set up a programming project before. Follow the steps in
order. Every command is typed into **PowerShell** (press the Windows key, type
`PowerShell`, press Enter).

There are two ways to run EZO:

- **A. Docker (recommended).** Only Docker Desktop is needed. Best for *using* EZO.
- **B. Developer mode.** Needed only when you want to *change* EZO’s code.

---

## A. Run EZO with Docker

### 1. Install the tools (once)

1. **Docker Desktop** — download from <https://www.docker.com/products/docker-desktop/> and
   install it. When asked, keep **“Use WSL 2”** selected. Restart Windows if it asks.
   Open Docker Desktop once and wait until it says *Engine running*.
2. **Git** — download from <https://git-scm.com/download/win> and install with the default
   options.

Alternatively, in PowerShell:

```powershell
winget install --id Docker.DockerDesktop -e
winget install --id Git.Git -e
```

Close and reopen PowerShell after installing.

### 2. Download EZO (once)

```powershell
cd $HOME\Documents
git clone https://github.com/UmidjanDeveloper/EZO.git
cd EZO
```

### 3. Create your settings file (once)

```powershell
copy .env.example .env
notepad .env
```

In Notepad, find the line `ANTHROPIC_API_KEY=` (or `OPENAI_API_KEY=` / `GEMINI_API_KEY=`)
and paste your key right after the `=` sign, with no spaces or quotes. Save and close.

> No key yet? You can skip this. EZO will start in **offline mode** and explain how to
> connect a provider.

### 4. Start EZO

Make sure Docker Desktop is running, then in the `EZO` folder:

```powershell
docker compose up --build
```

The first start downloads and builds everything and can take 5–10 minutes. When you see
lines like `web-1 | ✓ Ready`, open **http://localhost:3000** in your browser.

### 5. Everyday use

| What | Command (in the EZO folder) |
|---|---|
| Start EZO | `docker compose up` |
| Start without keeping the window busy | `docker compose up -d` |
| Stop EZO | `Ctrl+C`, then `docker compose down` |
| Get the newest version | `git pull` then `docker compose up --build` |
| Look at error messages | `docker compose logs api` |

Your conversations and memories are kept between restarts.

---

## B. Developer mode

Use this when you want to edit the code and see changes immediately.

### 1. Install the tools (once)

```powershell
winget install --id Python.Python.3.13 -e
winget install --id astral-sh.uv -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Docker.DockerDesktop -e
winget install --id Git.Git -e
```

Close and reopen PowerShell, then install pnpm:

```powershell
npm install -g pnpm
```

### 2. Check and set up

In the `EZO` folder:

```powershell
py scripts\ezo.py doctor
py scripts\ezo.py setup
```

`doctor` lists anything that is missing and how to install it. `setup` creates `.env` and
installs all dependencies.

### 3. Run

```powershell
py scripts\ezo.py dev
```

This starts the PostgreSQL database in Docker, applies database migrations, and runs the API
(<http://localhost:8000>) and the web app (<http://localhost:3000>). Code changes reload
automatically. Press `Ctrl+C` to stop.

**Without Docker:** open `.env`, replace the `DATABASE_URL=...` line with
`DATABASE_URL=sqlite:///./ezo.db`, and run `py scripts\ezo.py dev` again. EZO then uses a
simple file database.

### 4. Test

```powershell
py scripts\ezo.py test
```

To also run the browser tests, install the test browser once and use `--e2e`:

```powershell
pnpm --filter @ezo/e2e exec playwright install chromium
py scripts\ezo.py test --e2e
```

---

If something goes wrong, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
