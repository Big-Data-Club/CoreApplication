# Scalability and File Delivery Optimizations

## 1. Purpose

This note records the performance and rendering work completed after the
following scale-related symptoms were reported:

- the user-management page became slow as the number of users increased;
- a teacher with many courses waited too long for the course page;
- course discovery and other consumers expected complete, unbounded lists;
- opening a lesson containing a PDF had noticeable startup latency; and
- landing-page content appeared only after hovering over it.

The changes are designed to keep request cost bounded as data grows. They do
not claim a specific latency improvement without an environment-specific load
test. The source code and API definitions remain the authoritative contract.

## 2. Summary of changes

| Area | Previous behaviour | Current behaviour |
|---|---|---|
| User list | Loaded every matching user and resolved organisations per user | Database pagination/filtering/sorting plus one batched organisation lookup per page |
| Teacher course list | Returned all owned/co-taught courses and aggregated over the full result | Selects one page first, then aggregates enrolments only for that page |
| Published course list | Returned an unbounded visible-course result | Returns a filtered, bounded page with pagination metadata |
| Frontend list consumers | Assumed endpoints returned arrays | Consume paginated response objects; teacher list can append additional pages |
| Lesson deep link | Loaded content for every section to find one `contentId` | Fetches the target content directly and loads only its containing section |
| PDF viewer startup | Waited for an extra lazy JavaScript chunk before mounting the viewer | Includes `ContentViewer` in the learning route bundle |
| File transfer | Range streaming existed, but generic API middleware emitted conflicting no-cache headers | Preserves immutable caching, byte ranges, validators, `HEAD`, and conditional requests |
| Landing page | Background and content shared an ambiguous stacking level | Uses an isolated stacking context and explicitly places content above the background |

### 2.1 Implementation references

| Change | Root commit | Frontend commit | Main locations |
|---|---|---|---|
| User/course pagination | `bb0cfc2` | `f1856c3` | `auth-and-management-service/.../UserController.java`, `lms-service/internal/{handler,repository,service}/`, frontend user/course services and pages |
| PDF/file delivery | `449d3ab` | `de4af24` | `lms-service/internal/handler/file_handler.go`, `lms-service/internal/middleware/nocache.go`, frontend learning providers and file route |
| Landing stacking fix | parent submodule update | `5e05776` | `frontend/src/app/(landing)/layout.tsx` |

The frontend is a Git submodule. A frontend commit is not present in a parent
checkout until the parent repository's submodule pointer is updated.

## 3. User-list optimization

### 3.1 API contract

`GET /api/users` now performs pagination, search, filtering, and sorting on the
server.

Supported query parameters:

| Parameter | Default | Notes |
|---|---:|---|
| `page` | `0` | Zero-based page number |
| `page_size` | `50` | Clamped by the service to a safe range |
| `query` | empty | Searches name, email, or code |
| `team` | empty | Exact team filter |
| `type` | empty | Exact user-type filter |
| `role` | empty | Exact role filter |
| `sort_by` | `id` | Restricted to the service allow-list |
| `sort_dir` | `desc` | `asc` or `desc` |

Response shape:

```json
{
  "items": [],
  "page": 0,
  "pageSize": 50,
  "total": 0,
  "totalPages": 0,
  "hasNext": false
}
```

The auth API is zero-based. This differs from the LMS course APIs, which are
one-based. Clients must not reuse one page number without converting it.

### 3.2 Database work

`UserRepository.searchPage(...)` returns a Spring Data `Page<User>`, so the
database applies the filter, order, limit, and offset. Sorting fields are
validated before constructing `PageRequest`; arbitrary request values cannot
become entity sort expressions.

Organisation names previously risked an N+1 access pattern: one user query
followed by organisation lookups for individual users. The current flow is:

1. query one bounded page of users;
2. collect the IDs on that page;
3. fetch organisation names for those IDs in one projection query; and
4. assemble `UserResponse` objects from the in-memory lookup map.

For page size `P`, organisation-query count is constant instead of growing
with `P`.

### 3.3 Frontend behaviour

The user-management UI requests 15 rows at a time. Search is debounced by
300 ms, filters and sorting reset the UI to page one, and all operations are
sent to the server. Modal components and the bulk-file parser remain loaded on
demand so they do not inflate the initial user-list bundle.

The UI currently builds the team/type/role dropdown choices from the loaded
page. If the product requires globally exhaustive filter choices, add a small
facets endpoint; do not restore the unbounded user download.

## 4. Course-list optimization

### 4.1 API contracts

The following LMS endpoints are paginated:

- `GET /api/v1/courses/my`
- `GET /api/v1/courses`

Both accept `page` (one-based), `page_size` (default 20, maximum 100),
`category`, `level`, and `search`. `/courses/my` additionally accepts
`status`.

The LMS response remains inside the normal success envelope:

```json
{
  "success": true,
  "data": {
    "items": [],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 0,
      "total_pages": 0
    }
  }
}
```

This is a contract change from an unwrapped array. Every new consumer must read
`data.items` and `data.pagination`.

### 4.2 Bounded SQL work

The repository uses a page-first query shape:

```text
filter visible/owned courses
        -> order
        -> LIMIT/OFFSET page
        -> aggregate accepted enrolments for page IDs only
        -> join creator and count data
```

Previously, an enrolment aggregation could operate across the full matching
course set before the response was bounded. The new common-table-expression
queries keep returned rows and enrolment-count work proportional to the page,
apart from the separate count query required for pagination metadata.

The teacher query includes both owned and co-taught courses. Published-course
queries retain organisation visibility checks; pagination does not bypass the
existing authorization rules.

### 4.3 Indexes

Migration `V012__course_listing_indexes.sql` adds:

- `idx_courses_creator_created_page` for teacher course ordering;
- `idx_courses_published_page` for published-course ordering; and
- `idx_courses_org_published_page` for organisation-visible published lists.

The LMS also applies the small read-path index set asynchronously and
idempotently at startup through `EnsureReadPathIndexes`. Startup does not fail
if this best-effort operation cannot complete, but production should still
apply and track the migration normally.

### 4.4 Updated consumers

The frontend service layer exposes the paginated response rather than hiding
pagination. The teacher course screen loads 15 courses per request and appends
the next page. Student discovery sends server-side filters and pagination.
Admin statistics, leaderboard mapping, draft previews, user services, AI
course tools, and performance-test fixtures were updated to read the new
response shape.

When adding another course-list consumer, do not request `page_size=100` by
default merely to recreate the old behaviour. Choose the smallest page that
supports the UI and add explicit next-page handling.

## 5. Lesson and PDF startup optimization

PDF startup has two separate costs: locating the selected lesson and delivering
the file bytes. Both were addressed.

### 5.1 Direct lesson restoration

A URL such as:

```text
/lms/student/courses/42/learn?contentId=9001
```

previously expanded every section and called the section-content endpoint for
all sections until the content was found. For a course with `S` sections, the
deep-link path could generate `S` content-list requests.

The current path runs the course, section list, co-teacher list, and direct
`GET /content/{contentId}` requests concurrently. After validating that the
returned content belongs to one of the course sections, it:

- selects that content immediately;
- expands only its containing section; and
- loads only that section's content for sidebar navigation.

Deep-link content lookup is therefore one direct content request plus one
section-content request instead of one request per course section.

### 5.2 Viewer bundle waterfall

The learning route always needs `ContentViewer` when content is active. It was
previously loaded with a client-only dynamic import, adding a JavaScript chunk
fetch and evaluation step before the PDF iframe could mount. The route now
imports it directly. This trades a somewhat larger route bundle for an earlier
document request, which is the appropriate trade-off on the dedicated learning
route.

### 5.3 File delivery semantics

`GET /api/v1/files/serve/{filepath}` streams from storage through
`http.ServeContent`; it does not read the complete file into application
memory. The route now clearly supports:

- `Accept-Ranges: bytes` and `206 Partial Content` for browser PDF readers;
- `HEAD` on serve and download endpoints;
- `ETag` values normalized to valid quoted HTTP syntax;
- `Last-Modified` and conditional requests;
- `Cache-Control: public, max-age=31536000, immutable`; and
- inline rendering for PDF while unsafe/unrenderable file types remain forced
  to download.

The generic LMS `NoCache` middleware now skips file serve/download paths. This
prevents `Pragma: no-cache` and expired response headers from contradicting the
immutable file policy.

The Next.js file proxy used in development/serverless deployments now forwards
`Range`, `If-Range`, `If-None-Match`, and `If-Modified-Since`, preserves `206`
and `304`, supports `HEAD`, and does not attach a body to `HEAD` or `304`
responses. In the main production Compose topology, Traefik routes `/files/*`
directly to the LMS service, avoiding an unnecessary frontend application hop.

### 5.4 Storage and caching assumptions

The one-year immutable cache policy is safe only because uploaded object names
are timestamped/unique. Replacing bytes at an existing object path would make
clients retain stale content. A replacement must create a new path and update
the lesson metadata.

Range support lets the browser request only the byte regions it needs, but PDF
authoring still matters. Very large, image-heavy, or non-linearized PDFs can
remain slow. For such files, optimize images and use Fast Web View
(linearization) before upload. A future CDN or direct signed-object delivery
can reduce geographic/network latency, but is not part of this change.

## 6. Landing-page rendering fix

The fixed background used `z-0`, while the main landing content had no explicit
foreground stacking level. Browser compositing could draw the background over
ordinary sections; hover transitions created new layers and made content appear
to become visible only on hover.

The landing layout now:

- creates an isolated stacking context with `isolate`; and
- wraps the page content/footer in `relative z-10`.

The navbar remains at its higher fixed layer. This is a rendering correctness
fix, not a data-loading optimization.

## 7. Deployment and compatibility

Use this rollout order:

1. apply LMS database migrations;
2. deploy auth and LMS backends;
3. deploy the frontend submodule revision; and
4. deploy/update AI consumers that parse course lists.

Backend and frontend should be released together because the list response
shapes changed. A legacy frontend expecting a raw array will not render the
new paginated object correctly.

No data backfill is required. The new indexes are additive. On a large
production `courses` table, inspect lock duration and build impact before the
migration window; use the operations team's concurrent-index procedure if the
normal migration lock is unacceptable.

## 8. Verification

The pagination implementation was checked with:

- LMS `go test ./...` in a Go container;
- auth-service Maven compilation with JDK 21;
- frontend `tsc --noEmit --incremental false`; and
- Python bytecode compilation for the changed AI tools.

The file-handler change includes a unit test for ETag normalization. Before a
production release, rerun the complete current-tree checks because the final
Docker verification attempt for the PDF-specific changes was interrupted:

```bash
cd lms-service && go test ./...
cd auth-and-management-service && mvn test
cd frontend && pnpm exec tsc --noEmit --incremental false
```

Also validate an actual PDF through the deployed edge, not only against the LMS
container:

```bash
curl -I https://bdc.hpcc.vn/files/document/example.pdf
curl -sS -D - -H 'Range: bytes=0-1023' \
  https://bdc.hpcc.vn/files/document/example.pdf -o /dev/null
```

Expected evidence:

- `HEAD` returns no response body;
- the first response includes `Accept-Ranges`, a quoted `ETag`,
  `Last-Modified`, and immutable `Cache-Control`;
- the range request returns `206` with `Content-Range`; and
- reopening the same immutable URL is served from browser/edge cache where
  applicable.

## 9. Performance validation plan

Do not use row count or subjective UI feel as the only acceptance test. Record
before/after measurements with the same dataset and environment.

| Journey | Primary measurements | Scale dimension |
|---|---|---|
| Admin opens users | API p50/p95, SQL count/time, response bytes | users and memberships |
| Teacher opens courses | API p50/p95, rows scanned, DB CPU | owned/co-taught courses and enrolments |
| Student discovers courses | API p50/p95, response bytes | published courses and organisations |
| Student opens PDF lesson | click-to-first-page, TTFB, request count, bytes before first page | sections, PDF size/pages |
| Student reopens PDF | cache status, transferred bytes, time to first page | warm browser/edge cache |

Start with the approved smoke profile in
[`performance-tests/README.md`](../performance-tests/README.md). For PDF timing,
add browser telemetry or a controlled Playwright journey because k6 cannot
measure the browser PDF renderer's first visible page. Compare cold-cache and
warm-cache runs separately.

## 10. Remaining opportunities

Prioritize these only after measurements identify the next bottleneck:

1. use cursor/keyset pagination if very deep offset pages become slow;
2. add PostgreSQL trigram indexes if `%search%` dominates query time at large
   scale;
3. provide dedicated user-filter facets rather than deriving options from one
   page;
4. linearize or preprocess oversized PDFs during the asynchronous document
   pipeline;
5. place immutable files behind a CDN or generate short-lived direct object
   URLs if application/edge throughput becomes the constraint; and
6. add click-to-first-page and cache-hit dashboards before further tuning.

Avoid speculative preloading of every PDF in a course. It shifts latency into
large background downloads, wastes mobile bandwidth, and scales poorly for
courses with many documents.
