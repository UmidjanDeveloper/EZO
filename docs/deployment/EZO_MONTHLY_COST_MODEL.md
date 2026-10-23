# EZO monthly infrastructure cost model (2026-10-23)

- **Scope:** infrastructure only; AI API charges are excluded.
- **Target:** about $10 per month.
- **Rule:** nothing here is a checkout quote.

## Evidence quality

| Price source | How it was obtained | Trust |
|---|---|---|
| Supabase plan limits | Supabase docs, through the connected Supabase MCP, today | Official |
| Cloudflare R2 | Cloudflare docs (`/r2/pricing/`, last updated 2026-10-01), through the Cloudflare MCP | Official |
| Vercel Hobby | Vercel docs, through the Vercel MCP (single region, non-commercial) plus search summaries for quotas | Mixed |
| Render | Search summaries only: render.com is unreachable from this sandbox, and the connector has no pricing API | **Unverified** |
| Hetzner | Search summaries that **disagree** (CX23 between €3.49 and €5.49) | **Unverified** |
| Oracle Always Free | Earlier research: the A1 allowance was halved to 2 OCPU / 12 GB on 2026-06-15 (press reports) | **Unverified** |

Calculations use 1 EUR = 1.20 USD. Tax is shown separately because it depends on where the
owner is billed.

## Option A — Hetzner primary + Oracle A1 executor + Cloudflare R2 (recommended)

| Line | Low | High | Note |
|---|---:|---:|---|
| Hetzner CX23 (x86, 2 vCPU / 4 GB / 40 GB) or CAX11 (ARM) | €3.49 | €5.99 | Conflicting 2026 listings; check at checkout |
| Primary IPv4 | €0.50 | €0.50 | IPv6-only is possible but breaks some clients |
| Traffic | €0 | €0 | Includes 20 TB in EU locations (third-party source) |
| Hetzner snapshots or backups | €0 | €0 | Not used; R2 is used instead |
| Oracle A1 executor | $0 | $0 | Only if the account and capacity exist; not needed until native Student parsing is accepted |
| Cloudflare R2, Standard class, ≤10 GB-month, ≤1M Class A operations | $0 | $0 | Official free tier. Enabling R2 needs a payment method. |
| Domain | $0 | ~$1/mo | A free DNS name works with Let's Encrypt; a bought domain is optional |
| **Subtotal** | **≈ $4.79** | **≈ $8.39** | Before tax |
| With 19–20% VAT, if charged | ≈ $5.70 | ≈ $10.07 | The high end touches the ceiling |

**Verdict:** this option fits $10 if the actual Hetzner price is at or below about €5.50 and
VAT is not charged, or the cheaper listing holds.
- **Not verified:** the real checkout total, Hetzner stock, and the Oracle account, capacity
  and reclamation policy.
- Native Student parsing on Oracle stays an extra that can disappear without warning. That is
  acceptable because it fails closed.

## Option B — Render + Supabase + Vercel

**B-full (the full profile; no free-beta restrictions):**

| Line | Monthly | Why it is needed |
|---|---:|---|
| Render web service, Standard (2 GB) | $25 | The API is planned at 768 MiB; Starter has only 512 MB |
| Render persistent disk, 10 GB at $0.25/GB | $2.50 | The full profile refuses remote storage and needs a durable volume |
| Render background worker, Starter, for stored-text jobs | $7 | Workers are refused in free-beta; full needs them |
| Supabase Free (500 MB database, pausing, no included backup download) | $0 | Needs a free active slot; **both are used**, so pause one or go Pro ($25) |
| Vercel Hobby (web) | $0 | **Non-commercial only** |
| Render workspace fee | unknown | Sources conflict ($0 Hobby, or $19–25) |
| **Total** | **≥ $34.50** | **Over budget by at least $24.50**, more with Supabase Pro |

**B-free-beta (the existing `deploy/render-free-beta.yaml`):**
- **Cost:** $0.
- **Limits:**
  - the free-beta profile forbids AI keys, voice, workers and presentations;
  - Render Free spins down when idle;
  - Supabase Free projects pause after inactivity.
- **Verdict:** a demo, not EZO.

## Option C — considered and rejected

Moving only the web app to Vercel Hobby and keeping the API on the VPS saves about 384 MiB on
the box. It adds a cross-site setup and the non-commercial restriction, and no cost is saved.
The paid version (Vercel Pro) is $20 per seat.

## What does not fit in $10

- A fully paid two-host stack, with a paid executor: about $14–17 per month.
- A microVM-per-job K4 sandbox: it needs `/dev/kvm` (bare metal or nested virtualization),
  which no verified offer here provides.
- Managed backups:
  - Supabase Pro costs $25 per month.
  - Render Postgres starts at $6 per month plus storage, and it cannot host the full profile
    alone.

## Monthly formula to recheck at checkout

`(server + IPv4 + extra disk + backup storage beyond 10 GB + egress) × (1 + VAT) + card/FX ≤ $10`
