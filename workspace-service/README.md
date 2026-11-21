# BDC Workspace service

Owns spaces, user-defined fields, pages, access grants, comments, Yjs document state, database schemas,
records/views, private attachments, page history and named page-view analytics in its own PostgreSQL database.
It never reads Auth/LMS/Personalize databases. See
[the feature contract](../docs/features/WORKSPACE.md) and
[the architecture decision](../docs/adr/2026-11-05-collaborative-workspace.md).

## Run

Node 22+ and PostgreSQL 15+. Set `DATABASE_URL`, the same `JWT_SECRET` used by
Auth, and `WORKSPACE_ALLOWED_ORIGINS` (comma-separated exact browser origins).
`PORT` defaults to 8088. Use a **direct/session PostgreSQL connection**: the
cross-replica notification listener cannot use a transaction pooler.

```sh
npm ci
npm start
```

Forward SQL migrations run transactionally under an advisory lock at startup.
They depend on the migration ledger, not on whether any users exist. Users and
personal spaces initialize lazily from authenticated requests; startup does not
copy Auth users or read another service's database. `WORKSPACE_DB_POOL_MAX`
defaults to 6 (including one LISTEN connection), and accepts 2–50 connections.
Production sets `WORKSPACE_DATABASE_NAME=bdc_workspace`; startup verifies the
actual database name before migration or schema checks, rejecting an incorrectly
configured connection before creating tables. Local Compose expects `workspace`.

For separate migration/runtime credentials, run `npm run migrate` with the
Workspace database owner URL, then set `WORKSPACE_MIGRATE_ON_START=false` and
use a restricted runtime role. Startup then verifies all migration filenames
against the ledger before listening. Do not put Neon admin credentials in the
browser or use the pooled hostname for this listener.
`/health` checks process health, `/ready` checks PostgreSQL. REST lives at
`/api/v1/workspace`; only the frontend BFF should expose it to browsers.
`/workspace-ws` must be routed unchanged to this service.

For the existing local stack merge `docker-compose.workspace.yml` with
`docker-compose.yml`. Provide a workspace-only database password (URL-encode
reserved URI characters), Auth JWT secret, and exact allowed origins in the
local secret environment. Never commit their values.

## Verify

```sh
npm test
# Integration tests explicitly refuse databases other than workspace_test.
TEST_DATABASE_URL=postgresql://…/workspace_test npm test
```

With no test database, the integration suite reports skips. The implementation
was verified against real isolated PostgreSQL with no skipped cases. Tests use
injected fixture identities only in the test constructor; the normal entry point
always verifies BDC access JWTs. Browser checks live in `frontend/tests/workspace/`.

## Operational bounds

`GET /library` catalogs accessible pages, databases and records across spaces.
Query parameters: `tab` (recent/favorites/shared/private/all), `q`, `sort`
(title/creator/source/created/editor/edited/visited), `direction`, `limit`
(1–100; default 50), `offset` (0–100000), optional `parent`, `match` (all/any),
IANA `timezone`, and a JSON `filters` array (maximum 12 field/operator/value rules).
It returns `{items,total,next_offset}`. Read-only results neither update visits
nor record analytics. `GET /library/options` returns only the names/IDs of
creators and editors of accessible pages, without emails. Both routes remove
hidden ancestors/fields before pagination. Parent/field source metadata appears
only when independently accessible. Shared includes team spaces, shared personal
spaces and direct grants; private includes the owner's unshared personal pages.

Migration 008 permits a null last-visited timestamp for an unopened favorite and
adds catalog indexes. Page opens explicitly store their timestamp; favorite writes
retain existing visits and use NULL for a new preference. Deploy this service and
migration before the new frontend. Existing preference timestamps are preserved.

Page metadata accepts a nullable `cover_image_id` (migration 007). Only a PNG,
JPEG or WebP attachment already bound to the target page may be used. Cover reads
use the existing authenticated file endpoint and recheck current page access.
Duplicates copy both the cover reference and attachment bindings. Removing a
cover clears its reference; undo/history and other page bindings retain files.
Roll out the service and migration before the frontend that submits this field.

- 100 active user-created fields per space; field archive/restore preserves earlier page trash.
- 4 MiB encoded document state, 10 MiB per PNG/JPEG/WebP/PDF, 100 MiB attachments
  and 40 uploads/hour/user; 30 owned spaces.
- 600 REST calls/minute/user; 12 authenticated sockets/user, 200 total open
  sockets/process, at most 16 awaiting authentication. Pre-auth messages are
  limited to 2 KiB before JSON parsing, authentication times out after 5 seconds,
  and queued work is bounded by 32 MiB/process and 32 messages/socket. The
  transport frame cap is still 6.5 MB for authorized document recovery; admission
  limits bound aggregate pre-auth exposure. The ingress limits new handshakes to
  10/sec per peer IP with burst 20; configure trusted proxies before relying on
  forwarded client IPs. These are resource bounds, not a DDoS capacity claim.
- DB reads page records in batches of 200; the UI offers load more and states
  that filtering/sorting applies to loaded records.
- Automatic pre-edit versions at most once per ten minutes, plus manual versions.
  **Only four snapshots per page are retained**, across automatic/manual/restore
  snapshots. Migration 009 permanently removes older snapshots; back up any
  existing history first if needed. Operation/activity history is separate and
  this policy is not a total workspace storage quota.
  Archive is reversible and preserves rows/attachments; no automatic destructive
  retention policy is enabled. Explicit permanent deletion from the Recycle Bin
  requires a trashed target and space management. Shared attachments survive.

Back up the entire Workspace database, including binary attachments, grants,
versions and Yjs state. Restore into an isolated instance first. Never roll back
a document by replacing only its bytes: use the version endpoint, which changes
its generation and rejects stale editors. Monitor readiness, connection errors,
pending-save age in the client, DB growth, and PostgreSQL backup restoration.

## First production release

The existing production workflow builds `bdc-workspace:<SHA>` and selects only
Workspace when its service/manifests change. It reuses the Workspace checks as a
required gate; there is no second independent push/deploy workflow. Frontend
still publishes its own immutable image before the root pointer rollout.

Before pushing the merged release, provision a dedicated Neon `bdc_workspace`
database, `bdc-workspace-secrets` with `DATABASE_URL`, and `bdc-workspace-config`
with exact `WORKSPACE_ALLOWED_ORIGINS`. Auth's existing `bdc-secrets/JWT_SECRET`
must match the access-token signer. The deployment preflight rejects missing
Workspace configuration. Optional ConfigMap key `WORKSPACE_MIGRATE_ON_START`
selects migration-at-start (default) or pre-migrated restricted runtime (`false`).

For the initial default namespace, an operator can provision the two resources
once with the following commands. The private environment file contains only
`DATABASE_URL=...` for the dedicated direct TLS connection; do not commit it.
Replace the example origin with the actual frontend origin before running:

```sh
kubectl -n default create secret generic bdc-workspace-secrets \
  --from-env-file=/secure/workspace.env --dry-run=client -o yaml |
  kubectl -n default apply --server-side --field-manager=workspace-operator -f -
kubectl -n default create configmap bdc-workspace-config \
  --from-literal=WORKSPACE_ALLOWED_ORIGINS=https://your-domain.example \
  --dry-run=client -o yaml |
  kubectl -n default apply --server-side --field-manager=workspace-operator -f -
```

After configuration and review, commit/push the frontend merge to its main branch
first so its image is published. Then commit/push the root merge with that actual
frontend gitlink. The root pipeline builds/releases Workspace once and waits for
the frontend image; a local commit alone does not trigger GitHub Actions.

The pod starts only after all migrations, including 009/010, succeed. It has a
startup probe, a six-connection pool by default, no model download/AI worker, one
replica and `maxSurge: 0` to avoid a second Workspace pod on the small node.
Rolling this singleton briefly interrupts Workspace; browser drafts/reconnect
remain necessary. Set the appropriate ingress TLS/host at the existing edge.
Frontend runtime `WORKSPACE_SERVICE_URL` defaults to
`http://workspace-service:8088`. `WORKSPACE_AI_ENABLED` is **false by default**;
the frontend hides AI actions and its BFF rejects AI requests without calling
upstream. This does not disable AI elsewhere in BDC Hub.

Notebook conversion remains an explicit API copy, not a Kafka pipeline. The BFF
fetches only the signed-in user's source note. The user selects a personal/team
space, the backend requires destination editor access, and migration 010 scopes
idempotency by user/note/destination. Retrying does not overwrite a shared copy;
the original note stays intact. Deploy this backend before the destination UI.
Do not roll back to a pre-010 Workspace importer after applying that migration.

Team invitations and membership changes require the owner; invitation acceptance
never overwrites existing roles. Readers receive no roster emails. Page-only
guests see the owner and direct page grantees, not unrelated space members;
page/space managers may see the relevant roster emails.

The initial Workspace implementation is credited to `tranminhkhoi8407-dev` on
`feature/workspace`. Preserve the merge parents and original authors in both
repositories; do not squash/rebase their work or replace their Author fields.
Contributor recognition on GitHub also depends on the commits reaching the
default branch and the author identity being associated with their account.
