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
- 600 REST calls/minute/user; 12 concurrent sockets/user, 200 authenticated
  sockets/process; per-socket payload/rate/backlog bounds.
- DB reads page records in batches of 200; the UI offers load more and states
  that filtering/sorting applies to loaded records.
- Automatic pre-edit versions at most once per ten minutes, plus manual versions.
  Archive is reversible and preserves rows/attachments; no automatic destructive
  retention policy is enabled. Explicit permanent deletion from the Recycle Bin
  requires a trashed target and space management. Shared attachments survive.

Back up the entire Workspace database, including binary attachments, grants,
versions and Yjs state. Restore into an isolated instance first. Never roll back
a document by replacing only its bytes: use the version endpoint, which changes
its generation and rejects stale editors. Monitor readiness, connection errors,
pending-save age in the client, DB growth, and PostgreSQL backup restoration.

`k3s/workspace` is an opt-in manifest set. Supply an immutable image, a dedicated
database Secret and allowed-origins ConfigMap before applying. It is deliberately
not added to the existing production auto-deploy workflow. Frontend runtime
`WORKSPACE_SERVICE_URL` should be `http://workspace-service:8088`.
