# Backup and restore plan

- **Status:** procedure VERIFIED locally. Off-site target (R2) BLOCKED, because R2 is not
  enabled. REQUIRES OWNER APPROVAL.

## What is backed up

A matched pair is taken back-to-back by `deploy/primary/backup.sh`:
1. the `ezo` database, as a `pg_dump` custom-format dump (consistent snapshot);
2. the `/app/storage` volume (artifacts and versions), as a tar.

A `MANIFEST.sha256` records the hashes plus the Alembic head. Everything is encrypted with
**age to the owner's public key**:
- the primary host can create backups but **cannot decrypt** them;
- the private key stays offline with the owner, in a password manager or on paper.

## Verified locally (2026-10-23)

- Backup of a production-configured stack: one artifact created through the real API.
- `restore-check.sh`:
  - decrypts the archive and verifies both hashes;
  - restores into an **empty** throwaway pgvector container;
  - reports head `0021`, artifacts 1, users 1, versions 1 and 4 files.

A backup counts as valid **only** after such a restore check.

## Schedule and retention (proposed)

| Item | Proposal |
|---|---|
| Frequency | Nightly via a systemd timer or cron on the primary host (owner installs it) |
| Restore drill | Monthly, plus after every schema migration, by running `restore-check.sh` on the latest archive |
| Retention | 14 daily, 8 weekly and 6 monthly copies. Prune with an R2 lifecycle rule (14/56/180 days) or a dated prefix layout. |
| Size budget | Keep the total under 10 GB-month to stay in R2's free tier. Alert at 7 GB. |

## R2 layout and access (prepared; not created)

- Bucket `ezo-backups`, private, Standard storage class (the free tier excludes Infrequent
  Access).
- Object key format: `primary/YYYY/MM/ezo-<UTC stamp>.tar.age`. Upload with
  `rclone copy --immutable`, so an existing object is never overwritten.
- Credentials: an R2 **Object Read & Write** API token scoped to **this one bucket**. Note that
  this permission also allows deletes. Use it through the S3-compatible API only; Cloudflare
  notes that object-level tokens do not work against its REST API. Store it only in rclone
  config on the host (mode 600).
- Protection against a compromised host: add an R2 **bucket lock** rule. Cloudflare docs:
  "prevent the deletion and overwriting of objects … for a specified period", for example
  `wrangler r2 bucket lock add ezo-backups --name keep-14d --retention-days 14`. Lifecycle
  rules remove objects only after the lock period.
- Bucket versioning: R2 has no S3 versioning. Use immutable writes, the bucket lock and
  lifecycle rules instead.
- Egress from R2 is free. Class A operations (about 30 uploads per month) are far below the
  1M-per-month free tier.
- Cost alert: set a Cloudflare billing notification. **No charges are expected under 10 GB.**

## Disaster recovery (primary host lost)

1. Provision a new host (owner approval) and follow the activation checklist up to
   `bootstrap-secrets.sh`.
2. Start only `db` so that initdb creates `ezo_app` and `vector`.
3. Run `age -d` on the latest archive, then `pg_restore --no-owner` into `ezo`, then untar
   storage into the `ezo-storage` volume.
4. Start the rest. The API's migrations are no-ops at the same head, and the post-migration
   checks run.
5. Rotate `EZO_API_TOKEN` and the provider keys if the old host may be compromised.

## Not covered yet

- Supabase-hosted variants: a Free plan has no point-in-time recovery, so the same
  `pg_dump` approach is needed.
- Point-in-time recovery for the VPS database: WAL archiving is not configured. The recovery
  point is the last nightly backup.
