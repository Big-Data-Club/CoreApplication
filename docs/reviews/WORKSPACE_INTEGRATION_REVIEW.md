# Workspace integration review

Reviewed: 2026-11-21. Scope: the pending merge of `feature/workspace` into root
`main` (`ecce92a` + `d1aeca2`) and frontend (`c184ba6` + `97eb000`).
Owners: Workspace/backend maintainer, frontend maintainer and deployment operator.
Source of truth: `workspace-service/`, `frontend/src/features/workspace/`, the
Workspace BFF and `k3s/workspace/`. This is a review, not a deployment approval.

## Decision

Implementation follow-up: F1/F2/F3 are addressed locally with negative integration
tests. F4 is budgeted to the existing 5000-character contract and Workspace AI
is disabled by default in both UI and BFF. Snapshot history is capped at four
versions (migration 009); notebook copies support an explicitly authorized target
space (010). There is now a separate migration command and optional schema
verification at startup, plus selected production routing with a reusable test
gate. F5's total storage/operation-history bounds and F6's horizontal scale work
remain outside this first pilot. The original findings below describe the
reviewed branch before those fixes, not the current behavior.

Keep the feature, but do not enable it for production users unchanged. Resolve
F1 and F2 before exposing the service, and resolve the AI contract mismatch
before enabling the AI panel. Pilot with one replica and synthetic/staging users.
Wider rollout requires storage bounds, a connection budget and measured latency.
No source commit, production migration or deployment was performed in this review.

## Findings

### F1 — P1: invitations bypass owner-only team membership management

Location: [Sharing.invite/respond/grant](../../workspace-service/src/sharing.mjs).

The documented contract reserves team membership management to the owner.
`invite` requires access 4 (manager) for a space, whereas `grant` requires access
5. `respond` rechecks the sender at access 4 and upserts `space_members.role`
without protecting the existing owner row. A manager can therefore invite a new
account into the team. More seriously, a manager can invite the owner's email
with role viewer; if the owner accepts, their existing owner membership becomes
viewer. `spaces.owner_id` remains unchanged but the permission checks use the
membership role, leaving the owner unable to manage the space through the normal
API. This is not an unauthenticated takeover: the downgrade requires acceptance.

Reproduced on isolated PostgreSQL with synthetic identities: owner access changed
from 5 to 1 through the actual Sharing and Store methods.

Fix: require owner authority for space invitations at creation and acceptance;
protect the owner row independently; do not use invitation acceptance to silently
replace an existing membership role. Keep explicit role changes in the existing
owner-authorized path. Add HTTP regressions for manager invitations, owner
targets, existing memberships and sender revocation.

### F2 — P1: the WebSocket connection cap excludes pending authentication

Location: [attachRealtime](../../workspace-service/src/realtime.mjs), especially
the `sessions.size` admission check and the first-message authentication queue;
[edge route](../../k3s/workspace/ingress.yaml).

Only authenticated sessions enter `sessions`. While that set is below 200, the
server can accept an unbounded number of sockets awaiting authentication for up
to five seconds. Each accepts payloads up to 6.5 MB before JSON/auth validation.
The 8 MB per-socket queue bound does not bound aggregate memory. Origin checking
protects browser cross-site use, but non-browser clients can supply Origin.
The new ingress declares no rate/concurrency middleware.

This is a code-path finding, not a flood-test result. Fix with total open/pending
connection limits, admission/rate controls at the edge and a small pre-auth
message limit before parsing. Count/release pending sessions on every exit path.
Keep the single-use ticket and subsequent per-operation permission checks.

### F3 — P2: a page-only viewer can read the whole space membership directory

Location: [Sharing.members](../../workspace-service/src/sharing.mjs).

The method accepts page read access, then returns all space members' IDs, names,
emails and roles. A direct page grant is enough to see unrelated space members,
even without space membership. Reproduced with a page-only viewer receiving the
unrelated manager's email. This does not grant access to their other pages.

Fix: return a page-scoped, minimized roster to page-only guests. Reserve the
space directory and email visibility for independently authorized callers.

### F4 — P2: Workspace AI messages exceed the AI service input contract

Locations: [Workspace BFF](../../frontend/src/app/api/workspace/[[...path]]/route.ts)
and [ChatRequest](../../ai-service/app/api/agent_router.py).

The BFF accepts prompt length 2000 and selection/page text length 30000, then
concatenates both into `message`. The AI API caps `message` at 5000. A long page
can therefore produce a 422 response before inference. The document-state fetch
also transfers the base64 state even though this branch never uses it.

Fix: share the effective input contract and budget the selected text plus prompt
and framing before sending; use the authorized text projection without fetching
an unused binary document. Keep reference material distinct from the user's
instruction. Do not solve this solely by increasing the global API limit.
The length mismatch is confirmed statically; no paid AI call was made.

### F5 — P2: write amplification and unbounded retained history

Locations: [Documents.write](../../workspace-service/src/documents.mjs),
[Pages.snapshot/createVersion](../../workspace-service/src/pages.mjs),
[Files.upload](../../workspace-service/src/files.mjs) and SQL migrations.

Each accepted edit materializes Yjs state, saves the whole state (up to 4 MiB),
updates indexed search text and writes an operation record. Automatic snapshots
are spaced by ten minutes, but manual snapshots have no equivalent storage
budget. Operation/version/activity/visit history has no automatic retention or
per-space byte budget. The 100 MiB/user quota applies to attachments only.
Repeated manual snapshots can grow database storage rapidly even below the REST
request limit. Attachments themselves are stored as BYTEA in PostgreSQL.

Fix: add explicit per-space/user storage and snapshot budgets, bound manual
snapshot frequency and define operation retention consistent with retry
idempotency. Agree retention/archive policy before deleting history. Small
attachments in PostgreSQL can remain for a measured MVP; use private object
storage when attachment traffic/storage warrants it, preserving page ACLs.

### F6 — P2: current realtime fanout is expensive and presence is replica-local

Location: [realtime](../../workspace-service/src/realtime.mjs) and
[rollups](../../workspace-service/src/databases.mjs).

`refresh` checks every session's page permission for each debounced notification,
including sessions unrelated to the changed page, then reads/sends full state to
each matching session. Every session also gets a permission query every three
seconds. At 200 sessions that heartbeat alone is about 67 permission reads/sec,
before edits, client sync, REST and rollups. This is an arithmetic estimate, not
a capacity measurement. Rollups perform sequential per-record/per-relation reads.

PostgreSQL notifications support document refresh between replicas, but awareness
and peer_left only broadcast to the local `sessions` set. Users on different
replicas therefore do not have complete shared cursor/presence behavior.
Listener errors are swallowed/retried and `/ready` only checks `SELECT 1`;
readiness does not establish that realtime notification delivery works.

Fix: index local rooms by page, target document fanout, reuse one authorized
state read where appropriate, bound concurrent refresh work and batch rollups.
Keep revocation checks authoritative. Define cross-replica presence and observable
listener/reconnect behavior before scaling replicas; sticky routing alone does
not remove the need to handle reconnects/revocation. Start with one replica.

### F7 — P2: startup migration and runtime database privilege are coupled

Locations: [main](../../workspace-service/src/main.mjs) and
[migration runner/pool](../../workspace-service/src/db.mjs).

Startup always runs migration DDL using the same DATABASE_URL as REST/realtime.
An unapplied migration cannot run with a DML-only runtime role. The runner uses
an advisory transaction lock and a migration ledger, which is good, but it has
no checksum verification and uses the pool's 10-second statement timeout.

Fix: a separate migration command/job using an owner role, followed by a runtime
role with only required schema/table/sequence privileges and a startup schema
compatibility check. Do not silently grant a general Neon admin role to runtime.
Make pool limits configurable and budget them across all replicas/rolling pods.

## What is already good

- SQL values are parameterized; interpolated tables/columns/operators inspected
  in these paths come from server allowlists. No SQL injection was demonstrated.
- Page/space permissions are checked in backend methods, not only hidden in UI.
- JWT signatures/expiry are validated; WebSocket tickets are hashed, short-lived,
  consumed once, and bounded by identity expiry. Writes recheck current access.
- Document writes use row locks, transactions and operation IDs; acknowledgement
  follows persistence. Restores advance generation to reject stale editors.
- File MIME is inspected, active HTML/SVG uploads are excluded, downloads have
  restrictive headers and file reads recheck current page access.
- Formula evaluation uses a bounded parser, not JavaScript eval.
- The editor loads dynamically; service/domain files, frontend hooks/components
  and explicit migration files provide a reasonable maintenance structure.

This review is not a dependency penetration test, browser XSS audit, distributed
load test or proof that every authorization path is correct.

## Neon database and migration procedure

Recommended production database: `bdc_workspace`, owned by a dedicated
`bdc_workspace_owner` migration role. Use its own schema/tables, not the Auth/LMS
database. No vector/UUID extension is required by migrations 001–008. They create
24 application tables plus the runner's `workspace_migrations` ledger.
Use `workspace_test` in a separate disposable test environment; the integration
suite refuses any other database name and clears its fixture tables.

One Neon project can contain multiple databases, but databases on one compute
still share resources. A separate project gives stronger workload isolation when
needed. A separate database alone is not a CPU/memory isolation boundary.

For the current implementation, DATABASE_URL must be a direct TLS connection
(hostname without `-pooler`), copied securely from Neon Connect. LISTEN requires a
persistent session. A future split may use pooled REST connections plus a
dedicated direct listener; changing only the URL today breaks that assumption.
The current pool is max 12 per process, with one connection held for LISTEN.

Neon roles created through general admin interfaces may have neon_superuser
privileges. Use SQL-created restricted roles or explicitly restricted role
creation, and verify actual grants. After F7, runtime should not own schema DDL.
Until then, do not claim migration/runtime privilege separation exists.

After creating the new empty database, provide DATABASE_URL through the local
secret environment. From workspace-service, this runs the existing runner only,
checks the intended target first and never starts the HTTP service:

```sh
node --input-type=module <<'JS'
import { createPool, migrate } from './src/db.mjs';
if (!process.env.DATABASE_URL) throw new Error('DATABASE_URL is required');
const pool = createPool();
try {
  const { rows } = await pool.query('SELECT current_database() AS name');
  if (rows[0].name !== 'bdc_workspace') throw new Error('Wrong migration target');
  await migrate(pool);
  const applied = await pool.query('SELECT name FROM workspace_migrations ORDER BY name');
  console.log(applied.rows.map(row => row.name).join('\n'));
} finally { await pool.end(); }
JS
```

Do not individually paste SQL files into Neon without the migration ledger.
Run all 001–008, in order, using the runner. Existing files stay immutable;
future fixes use forward migrations. No Neon credentials or connection were
available in this review, so this procedure was NOT executed against Neon.

## Verification performed

- PostgreSQL 15 disposable Docker instance, loopback-only with synthetic users;
  container stopped/removed after checks. No production database was used.
- Formula tests: 2 passed. Integration tests: 41 passed, 0 skipped.
- Migrations 001–008 applied to the isolated DB; runner invoked twice again and
  ledger stayed at 8 entries.
- Additional isolated probes reproduced F1 owner downgrade and F3 directory leak.
- Workspace BFF tests: 7 passed. Tenant routing tests: 7 passed.
- Frontend scoped lint, formatting and TypeScript passed during merge preparation;
  Compose overlay and Kustomize rendering passed. Full browser/production build
  and Neon-specific network/failover behavior are not covered by these checks.

## Suggested integration order

1. Fix F1/F2/F3 and add negative authorization/admission regressions.
2. Fix F4; separate migration execution/runtime privilege for F7.
3. Add minimal storage/snapshot budgets for F5. Define recovery/backup procedure.
4. Provision dedicated Neon database and secrets, migrate, then pilot one replica.
5. Verify two-user editing, revocation, reconnect, restore, long-page AI and file
   download in staging. Set latency/storage/connection acceptance thresholds.
6. Fix/measure F6 before horizontal rollout. Do not infer capacity from pod limits
   or the existing ten-editor functional integration test.
7. After review approval, commit frontend first, publish its image, then record
   its actual merged commit in the root merge. Both remain uncommitted now.

## Primary provider references

- [Neon database management](https://neon.com/docs/manage/databases)
- [Neon pooled connection limitations](https://neon.com/docs/connect/connection-pooling)
- [Neon roles and privilege differences](https://neon.com/docs/manage/roles)
