# BDC Workspace — implemented behavior and verification

Entry: **Workspace**, immediately after Tasks in the main menu. Available to
authenticated BDC members. Uses the existing light/dark theme and mobile shell.

## User flows

| Area | Behavior |
| --- | --- |
| Fields | Workspace opens a user-created field gallery; arbitrary names, descriptions, 12 icons, 6 colors and tags; edit/trash/restore/permanent delete; no seeded disciplines |
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
actual interactions, recovery and sharing semantics. The six-dot menu of a child
page offers Move to Trash; it trashes the target branch and removes its link.

## Field hierarchy and existing content

The hierarchy is **Space → Field → Page → Subpage**. `/workspace` (optionally
`?space=…`) opens the gallery; `?field=…` opens that field and its first root page;
`?page=…` opens the authorized page directly. Creating a field explicitly creates
one root page named after it and stays on the gallery; opening the field is a
separate action. New personal/team spaces contain no starter pages
or predefined fields. Existing pages retain `field_id = null`; the gallery header
page picker opens them without a legacy footer.

“Trang mới” creates a root in the current field. Header “Trang con”
and `/page` create children. Child pages inherit the parent's field, including
database record pages. Moving a branch changes its field atomically, including
archived descendants. The destination parent must belong to the same space and
field; cycles and moves of individual database records are rejected. Real
children appear in their parent's content even if no explicit page-link block
was inserted. Page rows have no trailing +/menu controls; the header and six-dot
block menu provide the corresponding actions.

Fields use their space membership, not direct page grants. Archive requires
space management and hides all active pages in a field. Restore restores only
that archive batch, preserving earlier page trash. Up to 100 active fields per
space are supported. Forward migrations 004/005 retain existing pages and add
field hierarchy constraints plus committed block-author/time metadata.

The six-dot menu has search, nested conversion/colors, duplicate/move/delete,
collaboration tools and block activity. The +/slash menu groups media, notebook,
headings, text and equations. URL cards accept HTTP(S) only, and persist with the
shared document. Customize page provides an icon palette, cover previews and
full width. The standalone handbook has a contents rail and five numbered
sections, including the searchable formula library.

## Permission contract

Viewer reads; commenter adds discussions; editor changes content and record
values; manager changes shared structure and page sharing; owner controls team
membership. Trashing, permanently deleting or moving branches requires space management so an explicitly
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

## Verification updated on 2026-11-06

- 39 service cases passed with real isolated PostgreSQL, also inside the Node 22
  service image; no skipped integration cases.
- 21 frontend cases passed, including all 65 formula renders, BFF resource/identity
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

The Fields refinement was additionally checked against the built production
frontend with the real BFF/service on an isolated Docker network. Field creation,
hierarchy, both block menus, URL cards, persisted covers/icons, archive/restore,
handbook and light/dark/mobile flows passed without browser JavaScript errors.
The original collaboration/recovery/database browser suite also passed against
that image. The native development CSS-as-script regression was reproduced and
then smoke-checked with no runtime errors after retaining Next's development
chunk graph. Local SQL migrations 004/005 were applied after a fresh backup.

The chrome/activity refinement was checked against the rebuilt production image
on the same isolated test topology. All three browser suites passed without
JavaScript errors, including tooltip contrast, gallery stay-after-create,
cross-field tabs, sidebar resize/collapse persistence, real view statistics,
the original viewer-name controls and animated guide navigation. The original shared-edit,
offline recovery, role and database flows passed again on this image.
The main local frontend/service were recreated after another database backup;
migration 006 applied successfully. Both local entry ports (3000/3001) returned
healthy responses and accepted WebSocket upgrades. No production deployment was
performed.

## Workspace chrome and page activity

Owner: Workspace service and frontend feature. Header success text is hidden once
updates are acknowledged; pending/error/disconnected states remain visible.
“Đã sửa…” is derived from stored update timestamps. Hover/focus shows creator and
last editor; activation opens Updates/Analytics. Existing named versions remain
in the separate History section. The editor canvas no longer has the image/file,
URL and LaTeX quick buttons; these actions remain in +/slash and the sidebar guide.

The page tree can be dragged between 220–480 px (also limited by viewport),
collapsed by clicking its edge or Ctrl/Cmd+Backslash, and reopened from the tab
bar. Width/collapse preferences are stored per signed-in account. Mobile keeps
an overlay tree. Tabs retain order when selecting pages; + opens an access-checked
cross-field picker with source labels, text preview, keyboard selection and new
page action. Closing the active tab selects a neighbor. Guide links smoothly
scroll the guide's own container, with a current-section marker and reduced-motion
support. Field cards have hover/press feedback; opening a field animates the editor.

Migration `006_page_analytics.sql` adds Workspace-owned visits and per-page viewer
privacy preferences. Only an explicit foreground page open posts `/pages/:id/view`.
Metadata polling and picker previews do not record a view. A transaction/advisory
lock deduplicates the same account/page for five minutes, including concurrent
requests. Counts are grouped by UTC date for 7/28/90-day windows. Visits start
when enabled; no historic figures are invented.

Viewer names are shown by default to authorized page readers, as requested in the
2026-11-06 refinement. The name-visibility checkbox/API has been removed. Legacy
preference rows are retained for compatibility with database backups but are no
longer read or written. Internal viewer account IDs remain absent from responses.
Every analytics read/write rechecks page access. No third-party analytics is used.

## Recycle Bin refinement (2026-11-06)

The gallery and page sidebar open the same Recycle Bin. It groups fields and
independent page branches, supports search, restore and permanent deletion with a
confirmation that names the selected item. Restoring a field preserves earlier
individual page trash. Archived children are grouped under their archived parent.

DELETE /pages/:id and DELETE /fields/:id require space management and an already
trashed target. A space transaction lock serializes tree changes. Deletion removes
all descendants, including earlier trash, document state, history, comments,
grants, notifications and analytics. Attachments shared with surviving pages are
retained; only newly orphaned attachments from the selected branch are deleted.
A foreign-key error rolls back the entire operation. No automatic deletion or
empty-all action is enabled. Permanent deletion cannot be undone in the UI.

The color submenu is 280 px wide, scrolls within the viewport and keeps labels on
one line. Block deletion has a trash icon. Redundant sidebar toggle, page caption
and gallery footer were removed; page search remains available in the gallery
header. The editor's header toggle and resize edge remain available.

The Recycle Bin refinement passed 39 service cases (native Node and the Node 22
image), 21 frontend cases, Workspace lint/type checks and the production build.
Four full browser suites passed on the rebuilt application, including actual
restore/purge/cancel flows and two-account collaboration. The final guide copy
and a mobile color-menu clipping correction were then checked on the final
image with browser-layout.py (390 px viewport, menu inside all four bounds).
Existing local Workspace data was backed up before refreshing the two local
application containers. The tests use only isolated fixture accounts/data.
