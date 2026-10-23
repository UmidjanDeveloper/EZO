# Cloud connector inventory (P9 preparation, 2026-10-23)

- **What this is:** every connector call made during this preparation, and what each one
  returned.
- **Read-only:** no write tool was called on any provider.
- **What was not done:** no resource was created, changed, paused or deleted, and no
  deployment, billing change or credential was made.
- **Branch:** `claude/p9-infra-preparation`, based on the integration branch at `518786a`.

Resources found on the owner's accounts that are **not part of EZO** are summarised without
names in this file. That keeps unrelated project names and identifiers out of the repository.
The owner received the full list in the chat report.

## Status

| Provider | Connection | Work status | What was actually inspected |
|---|---|---|---|
| GitHub | **CONNECTED** (scoped to `UmidjanDeveloper/EZO`) | VERIFIED | Integration branch head, branch push and pull request. No settings, rulesets or protection were touched. |
| Supabase | **CONNECTED** | VERIFIED (read) / CONFIGURATION PREPARED | `list_organizations`, `get_organization`, `list_projects`, docs search. |
| Render | **CONNECTED** | VERIFIED (read) / CONFIGURATION PREPARED | `list_workspaces`, `list_services`, `list_postgres_instances`, `list_key_value`. |
| Vercel | **CONNECTED, user scope only** | BLOCKED for project and domain inspection | `get_auth_user` works. `list_projects` and `list_domains` return **403** for team scope `umidjans-projects`. `authorize_team_access` was refused for this token. Docs search works. |
| Cloudflare (Developer Platform MCP) | **CONNECTED** | R2 **BLOCKED** (not enabled) | `workers_list` returns 0 Workers. `r2_buckets_list` returns error **10042**, "Please enable R2 through the Cloudflare Dashboard". The vendor marks this MCP server as deprecated. |
| Oracle Cloud | **UNAVAILABLE** (no connector) | REQUIRES OWNER ACTION | Nothing. Tenancy, quota and capacity are unverified. |
| Hetzner | **UNAVAILABLE** (no connector) | REQUIRES OWNER ACTION | Nothing. Prices come from third-party search results (see the cost model). |
| Datadog (monitoring) | **AVAILABLE BUT NOT CONNECTED** (needs sign-in) | Not used | Nothing. |
| Context7 / vendor docs | CONNECTED | Used for documentation | Supabase, Vercel and Cloudflare docs searched for limits and pricing. |

## Findings per provider

### Supabase (organization on the Free plan)
- **No EZO project exists.**
- The organization has **4 unrelated projects**:
  - 2 are `ACTIVE_HEALTHY` in `eu-central-1`, on Postgres 17.6.1.166;
  - 2 are `INACTIVE` (paused) in `ap-northeast-1`, on Postgres 17.6.1.063 and 17.6.1.084.
- **Free plan limits (Supabase docs, checked today):**
  - 2 free active projects across all organizations the owner administers. Paused projects
    do not count.
  - 500 MB database per project; the database becomes read-only above that.
  - 1 GB Storage and 5 GB egress.
  - Pausing after 7 days of low activity.
- **Consequence:** a new EZO project on Free needs one of the two active projects to be
  paused first, or an upgrade to Pro. Either is an owner decision; neither was done.
- **Write tools were deliberately not used.** The connector exposes `create_project`,
  `apply_migration`, `execute_sql`, `pause_project` and `create_branch` (branching is
  billable). None of them was called.

### Render (one workspace)
- 1 **unrelated** free web service, region Oregon.
  - **`autoDeploy: yes`, triggered on every commit.** The owner should know this.
  - It was not touched.
- 0 Postgres instances and 0 Key Value instances.
- **No root `render.yaml` exists in EZO**, so no Blueprint can be auto-discovered from this
  repository (a unit test now enforces that).

### Vercel (user on the Hobby plan)
- The account's default team is `umidjans-projects`, and the connector lacks that scope.
- So **existing projects, domains and Git links were not inspected.**
- The Hobby plan is for non-commercial use only (Vercel docs).

### Cloudflare
- R2 is not enabled on the account.
- Enabling it is a dashboard action that adds a payment method and billable product lines,
  even though usage within 10 GB-month is free. That needs owner approval (see the
  activation checklist).

## Owner actions that unlock more inspection

These are not credentials. Never paste keys into chat.

1. **Vercel:** in claude.ai → Settings → Connectors → Vercel, reconnect and grant access to
   the team `umidjans-projects`. Then project, domain and Git-link inspection can be re-run
   read-only.
2. **Cloudflare:** decide whether to enable R2 (checklist step R2). Only after that can
   buckets be listed.
3. **Oracle and Hetzner:** no connector exists. The owner checks quotas and prices in their
   consoles (checklist steps H1 and O1).
