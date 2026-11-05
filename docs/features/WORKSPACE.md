# BDC Workspace — implemented behavior and verification

Entry: **Workspace**, immediately after Tasks in the main menu. Available to
authenticated BDC members. Uses the existing light/dark theme and mobile shell.

## User flows

| Area | Behavior |
| --- | --- |
| Spaces | Private personal space; named team spaces; email-bound in-app invitations |
| Pages | Parent/child tree; create/rename/move; favorites, recents, permission-filtered search; icon/cover/full width; tabs and side peek |
| Editor | Slash menu, block drag handle, turn into, colors, duplicate, move up/down, block links, child pages, text/code/checklists/tables, image/PDF upload |
| Mathematics | Inline `$$…$$` input; `/math` block equations; safe KaTeX with mhchem; searchable 65-example guide, practice preview, copy/insert; Markdown export preserves formula source |
| Collaboration | Yjs shared editing and cursors, durable save states, local recovery after interruption, permission changes and generation-aware version restore |
| Discussion | Block/page comments, replies, resolve/reopen/delete by author/manager, explicit member mentions and in-app notifications |
| History | Manual named versions, automatic pre-edit versions, activity log, restore with pre-restore backup |
| Databases | Table/Board/Calendar/List/Gallery/Timeline on the same records; date ranges, status, labels, people, checkbox, URL, numeric/text, relation, bounded formula and rollup |
| Database controls | Personal/shared views, visible fields, AND filters, sort, status grouping, date field, record search, load more; protected structure changes |
| BDC integrations | Idempotent old-notebook conversion, AI answer save button, course/lab/Studio links, permission-filtered canonical Tasks previews/links, access-checked backlinks |
| Transfer | Add Markdown/text to current page; export current page as Markdown; duplicate selected page content; archive/restore complete branches |

The guide at `/workspace/guide` is available independently, and opens inside
Workspace without unmounting the editor when inserting a formula. It describes
actual interactions, recovery and sharing semantics. Removing a page-link block
removes the reference; archiving pages is an explicit page-menu operation.

## Permission contract

Viewer reads; commenter adds discussions; editor changes content and record
values; manager changes shared structure and page sharing; owner controls team
membership. Archiving/moving branches requires space management so an explicitly
shared page cannot become a route to hidden descendants. A copied URL grants no
access. Team membership never follows automatically from a user's organization,
team name, chosen template or BDC admin role. Task permissions follow the original
creator/assignee/admin relationship; Workspace access does not expand them.

Invitations are in-app, recipient-bound, expire after seven days and recheck the
sender's authority on acceptance. No email sending or public publishing is wired.
Views/records contain relation IDs, but related titles and rollup values require
source access. Attachments require access through a bound page on every read.
Numeric rollups aggregate stored Number fields; Count counts related records.
Restoring a record version rejects properties incompatible with the current
schema, preserving the current document instead of reintroducing invalid values.

## Data ownership and APIs

`workspace-service` owns all new persistence. Auth remains identity/Tasks owner;
LMS remains course owner; Lab owns submissions; Personalize owns legacy notebook
entries. Browser REST: `/api/workspace/**` through NextAuth BFF. Internal REST:
`/api/v1/workspace/**`. Socket: `/workspace-ws`. See service source for validated
schemas and the ADR for the consistency/security design. No new Kafka topic or
cross-service table access is introduced.

## Local verification

Backend: `workspace-service/npm test`, with `TEST_DATABASE_URL` pointing to the
isolated database named exactly `workspace_test`. Frontend:
`node --test tests/workspace/*.test.cjs`, TypeScript, ESLint and production build.
`frontend/tests/workspace/browser-e2e.py` drives only the owned local app in
headless Edge. It verifies real session/BFF authorization, shared editing, offline
recovery, equations, comments, permission downgrade, record views and mobile.
`prepare-browser.mjs` creates short-lived signed test cookies from a generated
local configuration; it refuses non-local/non-test configurations. No test
password, signing secret or cookie belongs in the repository.

## Practical boundaries

This implements the requested core Workspace, not every product in Notion's
ecosystem. Public sites, Notion account migration, external guests without BDC
accounts, email delivery, automations, enterprise audit exports, full offline
initial opening, and a general Notion-compatible formula language are not part
of this contract. Timeline is a dated-record overview; database records load in
200-row batches and client filters apply to loaded rows. Duplication copies the
selected document; it does not recursively clone an entire space or all database
records. Page history does not version database schema changes.

Production is not deployed by this change. Use the opt-in Compose/K3s manifests
and the service runbook; configure dedicated database credentials and backups,
exact origins, the frontend runtime service address and the WebSocket edge route.

## Verification recorded on 2026-11-05

- 30 service cases passed with real isolated PostgreSQL, also inside the Node 22
  service image; no skipped integration cases.
- 15 frontend cases passed, including all 65 formula renders, BFF resource/identity
  checks, canonical Task visibility and the production WebSocket rewrite.
- Workspace ESLint and TypeScript checks passed. The full frontend production
  build passed; existing unrelated lint warnings remain in the wider application.
- Headless browser checks passed for two-account editing, actual disconnection and
  recovery, title conflicts, block/inline formulas, private Unicode-named files,
  comments, version restore, role downgrade, database views, and light/dark/mobile.
- Compose and Kustomize render checks passed. These correctness checks do not
  constitute production load/capacity certification.
- The local Docker frontend and Workspace service are healthy. The production
  frontend image was rebuilt, and WebSocket upgrade checks passed through both
  localhost ports 3000 and 3001. Existing local Workspace data was backed up
  before the update. AI and old-notebook live checks still depend on their
  existing BDC services being available.
