# Local companion lifecycle and revocable authority

This extends the fixed Linux metadata operation, not remote pairing, a general
sandbox, Windows support or durable multi-step orchestration. The API does not
launch the companion. Trusted local operators supply configuration and key FD.
No model-generated request gains a new action or control parameter.

## Durable state and commit points

`metadata_requests`: absent → started → completed_metadata_scan | cancelled |
revoked | interrupted. IDs are never revived. A crash may leave `started`; replay
is rejected and no completion is invented. The receipt is a hash of the actual
signed-result payload; filenames/bodies are not stored in the journal.

`metadata_cancellations`: request UUID and first cancellation time. A tombstone
may precede admission and survives restart. Up to10000 tombstones; no automatic
retention reset. Repeating the same cancellation remains idempotent at the limit.
Completed/interrupted/revoked historical requests return `already_terminal` and
are not rewritten by cancellation. Cancelling a running request marks it cancelled.

`metadata_controls`: permanent journal-wide revoked flag and first revocation time.
Revocation rejects new request IDs and fences started requests. It preserves
already-terminal history. Repeating revocation does not clear it or change its
original time. No reset/re-enable operation is exposed. Deleting/replacing local
state is not a supported recovery procedure; a host owner can tamper with files,
so this is not a cryptographically tamper-proof log or protection from a compromised OS.

Admission, cancellation, revocation and final publication serialize using SQLite
`BEGIN IMMEDIATE`. Reads check persistent controls before/between scan operations.
Final publication rechecks controls and deadline under the write lock, commits
receipt/status, and only then returns a signed response. A cancel/revoke committed
before this point prevents completion; one committed afterward cannot retract a
previously completed observation or data already delivered. No claim of atomic
revocation of an in-flight OS syscall or stdout is made.

Cancellation/deadline checks are cooperative. A stalled filesystem operation still
requires an external hard-stop/controller; this is not K4 containment. A lock error
fails closed rather than proceeding with a successful result. A crash after the
completion commit but before stdout leaves terminal history; there is no automatic
re-execution or result recovery API. The operator must investigate ambiguous delivery.

## Operator controls

Use the same trusted root/journal/identity/key-FD arguments as the normal module
invocation, with exactly one additional flag:

- `--cancel-request <request-uuid>`: local persistent cancellation, no stdin request
  needed. Returns `cancelled` or `already_terminal`, never a fabricated tool result.
- `--revoke`: revoke this journal's bound authority permanently. Returns
  `authority_revoked`. Other open companion instances observe the committed state.

These are local operator commands, not remotely accepted model tools, a permission
creation API, or proof of remote owner authentication. Keys remain in inherited
file descriptors and are neither generated nor printed by the companion.

## Journal compatibility and rollback

Wire protocol remains v1, unchanged. Companion journal is v2 (separate from API
Alembic0019). Valid v1 EZO1 journals upgrade transactionally, preserving identity,
request IDs and receipts. Foreign databases, missing binding/replay tables and
incomplete v2 control state fail closed. Do not clear or reset the journal to
recover from errors. Old v1 binaries reject the v2 header rather than silently
ignoring newly recorded revocation; downgrading this journal is unsupported.

## Evidence

`apps/api/tests/integration/test_companion_metadata.py` exercises actual Linux
files, independent SQLite connections, a real operator subprocess, persistence
across restart, pre-admission/in-flight cancellation, revocation, terminal receipt
integrity, bounded tombstones, transactional v1 upgrade, incomplete state rejection
and a real process crash after admission. No OS/filesystem mocks or production
keys are used. This does not prove Windows, mobile, Chrome, voice or Telegram E2E.
