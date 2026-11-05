# BDC Workspace service

Owns spaces, pages, access grants, comments, Yjs document state, database schemas,
records/views, private attachments and page history in its own PostgreSQL database.
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

- 4 MiB encoded document state, 10 MiB per PNG/JPEG/WebP/PDF, 100 MiB attachments
  and 40 uploads/hour/user; 30 owned spaces.
- 600 REST calls/minute/user; 12 concurrent sockets/user, 200 authenticated
  sockets/process; per-socket payload/rate/backlog bounds.
- DB reads page records in batches of 200; the UI offers load more and states
  that filtering/sorting applies to loaded records.
- Automatic pre-edit versions at most once per ten minutes, plus manual versions.
  Archive is reversible and preserves rows/attachments; no automatic destructive
  retention policy is enabled.

Back up the entire Workspace database, including binary attachments, grants,
versions and Yjs state. Restore into an isolated instance first. Never roll back
a document by replacing only its bytes: use the version endpoint, which changes
its generation and rejects stale editors. Monitor readiness, connection errors,
pending-save age in the client, DB growth, and PostgreSQL backup restoration.

`k3s/workspace` is an opt-in manifest set. Supply an immutable image, a dedicated
database Secret and allowed-origins ConfigMap before applying. It is deliberately
not added to the existing production auto-deploy workflow. Frontend runtime
`WORKSPACE_SERVICE_URL` should be `http://workspace-service:8088`.
