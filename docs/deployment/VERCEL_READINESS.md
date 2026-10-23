# Vercel readiness (web, `apps/web`)

- **Connection:** CONNECTED (user scope).
- **Status:**
  - CONFIGURATION PREPARED;
  - BLOCKED for inspecting existing projects (team-scope 403);
  - REQUIRES OWNER APPROVAL to create a project.

In the recommended architecture A, the web app runs on the primary VPS behind Caddy, so
**Vercel is optional**. Prepare it only if the owner prefers Vercel's CDN for the UI.

## Account facts

- The user plan is **Hobby**. Vercel's terms allow **non-commercial use only**.
- The default team is `umidjans-projects`. Projects and domains could not be listed (403), so
  it is unknown whether an EZO project or Git link already exists.

## Prepared configuration (`apps/web/vercel.json`)

```json
{
  "framework": "nextjs",
  "installCommand": "cd ../.. && pnpm install --frozen-lockfile",
  "buildCommand": "pnpm build",
  "regions": ["fra1"],
  "git": { "deploymentEnabled": false }
}
```

- **`git.deploymentEnabled: false`**, per Vercel's git-configuration docs, turns off
  automatic deployments for **all branches**. Connecting the repository therefore cannot
  start builds by itself. A unit test (`test_deployment_configs.py`) keeps it that way.
- **Root Directory:** `apps/web`. This is a project setting, not a `vercel.json` field.
  Install runs at the monorepo root, so the pnpm workspace packages `@ezo/ui` and
  `@ezo/shared` resolve. They are transpiled (`transpilePackages`).
- **Region:** `fra1`, close to the API in the EU. Hobby allows one region.
- **`output: "standalone"`** in `next.config.ts` is for the Docker image. Vercel builds Next
  normally either way.

## Environment variables (Vercel project settings, never in Git)

| Name | Environments | Notes |
|---|---|---|
| `EZO_API_URL` | Production, and Preview if wanted | **Runtime, server-only.** Must be an exact HTTPS origin, for example `https://api.<domain>`. It is injected into the page through `/ezo-config` and the CSP. A wrong value makes the page fail closed (validated locally). |

- There are **no** other variables. The browser never needs an AI key or a database URL.
  The owner's API token is typed into the app, and stored in the browser's localStorage.
- Add the Vercel domain to the API's `EZO_CORS_ORIGINS`. It must be an exact HTTPS origin;
  wildcards are refused by `deployment.py`. Preview URLs change per deployment, so either
  leave Preview without API access or add a fixed alias.

## Security and operation

- **Deployment Protection:** enable Vercel Authentication for Preview deployments.
- **Production branch:** set it to the integration branch only after the owner approves.
- **Rollback:** Hobby can roll back only to the immediately preceding production deployment
  (`vercel rollback`, per the docs). Keep the VPS web container as the fallback.
- **CSP:** a per-request nonce comes from `proxy.ts`, so do not add caching that strips
  headers.

## Owner steps (later)

1. Grant the connector the `umidjans-projects` team scope so the account can be inspected.
2. Approve project creation. Then create the project with root `apps/web`, link the
   repository (no deploys run, because `deploymentEnabled` is false), and set `EZO_API_URL`.
3. Approve one manual production deployment (`vercel deploy --prod` from a reviewed commit).
