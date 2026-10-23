# Owner activation checklist (P9) — every external step needs its own approval

- **State today:** P9 is **prepared, not deployed**.
- **Launch-ready:** **no.** The application has not passed acceptance on a real host.
  Native parsing and K4 remain blocked.
- **How to read this list:** each step names the service, the exact action, the expected
  cost and the risk. Approving one step does not approve the next.

## A. Decisions (no cost)

| # | Decision | Recommendation |
|---|---|---|
| D1 | Architecture | **A**: Hetzner primary + R2 backups, with the Oracle executor later. See the cost model. |
| D2 | Domain | Use an existing domain or subdomain, or a free DNS name. Buying one is optional (step N1). |
| D3 | AI providers for launch | Start with one provider (for example Gemini) with a console budget cap. |

## B. External actions that need approval

| # | Service | Exact action | Cost | Risk |
|---|---|---|---|---|
| V0 | Vercel connector | Reconnect it with team `umidjans-projects` scope (read-only inspection) | $0 | None. **Optional:** Vercel is not needed for architecture A. |
| H1 | Hetzner | Create a project; order CX23 (or CAX11) in an EU location with 1 IPv4; add the owner's SSH key; firewall 22 (owner IP only), 80, 443 | ≈ €4–6.50/mo + VAT if charged | Billable from creation. Stock may be unavailable. |
| H2 | Primary host | Install Docker; `git clone`; run `deploy/primary/bootstrap-secrets.sh`; copy and edit `primary.env`; run `sudo chown 999:999 secrets/db-tls/server.key`; move `ca.key` offline | $0 | Secrets are created on the host only |
| N1 | DNS | Create A records for `EZO_WEB_DOMAIN` and `EZO_API_DOMAIN` pointing to the host IP | $0 (≈$1/mo if a domain is bought) | Changes DNS |
| L1 | Launch | `docker compose --env-file secrets/compose.env --env-file primary.env up -d --build` on a **reviewed commit with green CI** | Included in H1 | First production start. Migrations run once. |
| L2 | Acceptance | Health, 401/200 auth, CORS, Office DOCX create and download, a Student TXT job processed by the worker, `restore-check.sh` passing. Then a 7-day memory and CPU sample with `scripts/benchmark_owner_stack.py`. | $0 | Do not announce until it passes |
| R2 | Cloudflare | Enable R2 (adds a payment method); create the private bucket `ezo-backups`; add a 14-day bucket-lock rule; create a bucket-scoped Object Read & Write token; configure rclone on the host; set a billing notification | $0 within 10 GB-month | Enabling makes R2 billable above the free tier |
| B1 | Backups | Generate the age key **on the owner's machine** and keep the private key offline; put only the public key on the host; install the nightly timer for `backup.sh`; run `restore-check.sh` monthly | $0 | Without a passed restore check, there is no backup |
| P1 | AI providers | Create API keys; **set hard spend limits in each console**; add the keys to `primary.env`; restart the API | Pay per use | Billable calls start with the first chat |
| O1 | Oracle Cloud (later) | Check the A1 quota and capacity in Limits, Quotas and Usage | $0 | Account, card and terms |
| O2 | Executor (later, after the arm64 CI job and the WireGuard change are reviewed) | Create the A1 VM; install Docker; build the executor image; run the isolated-executor acceptance | $0 if within Always Free | Reclamation, capacity |
| S1 | Supabase (only if the free-beta demo or managed Postgres is chosen) | Pause one existing active project, **or** upgrade to Pro ($25/mo); then follow SUPABASE_READINESS.md | $0 / $25 | Pausing affects that other project |
| RD1 | Render (only for the free-beta demo) | Import `deploy/render-free-beta.yaml` manually, enter its secrets, run one manual deploy | $0 (Free) | Public endpoint; cold starts |

## C. Never without a separate, explicit decision

- Merging to protected branches.
- Changing GitHub branch protection.
- Enabling auto-deploy on any platform.
- Pushing migrations to a remote database outside the API entrypoint.
- Enabling OCR or LibreOffice in the API.
- Enabling the K4 sandbox.
- Uploading real user data before a restore check has passed.
