# JARVIS frontend contract and open backend requests

Frontend/extension only. This document does not add or authorize any backend behaviour.

## Endpoints the frontend uses (canonical, `apps/api/src/ezo_api/api/routes/jarvis.py`)

| Route | Used by | Notes |
|---|---|---|
| `GET /api/jarvis/capabilities` | web `/jarvis` | Rendered as-is. `available:false` → "Not available". Even `available:true` is shown as "execution not authorized" because `execution_authorized` is always `false`. |
| `POST /api/jarvis/percentages` | web `/jarvis` | Deterministic calculation on user-typed values. Response must pass strict shape validation or nothing is shown. |
| `GET /api/jarvis/receipts/{id}` | declared in the contract table, not yet called | |
| `POST /api/jarvis/inspect-plan` | declared in the contract table, not yet called | |
| `GET /api/health` | Chrome extension | Reachability only. Never displayed as paired/connected/authenticated. |

`apps/web/lib/jarvis-contract.test.ts` parses `jarvis.py` and fails if the web app or extension references any
`/api/jarvis/*` path the backend does not declare.

## Removed (never existed in the canonical backend)

`/api/jarvis/companion/status|files|setup-scenario`, `/api/jarvis/plan`, `/api/jarvis/tasks[/{id}/execute|authorize|cancel]`.
The matching UI (plan/execute, approve & dispatch, "Paired" badge, Downloads browser, Telegram receipt,
PDF download button, mic toggle, hard-coded recipient, offline "paired device" fallback) is gone.

## Chrome extension permissions

`activeTab` + `scripting`; optional host access limited to `http://localhost/*` and `http://127.0.0.1/*`, requested
only on a click. No `content_scripts`, no background worker, no notifications, no polling. Reading the tab happens in a click
handler through `chrome.scripting.executeScript` under `activeTab`.

## Needed from Codex / Claude before any of this UI can return

Nothing below is implemented or simulated on the frontend. Request, don't build:

1. Authenticated device pairing/enrolment API (list devices, pairing state, revoke) with verified heartbeat.
2. Durable task create / status / cancel API with server-verified step outcomes.
3. Scoped, revocable approval API for external dispatch.
4. Office→PDF worker with output verification, and Telegram integration with provider-verified delivery receipts.
5. An extension pairing + per-site grant API (extension currently has no way to authenticate).
6. A genuine device → PDF → Telegram acceptance test. Until it passes, JARVIS Mode is not described as operational.
