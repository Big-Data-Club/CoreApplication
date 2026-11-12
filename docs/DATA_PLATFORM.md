# BDC Hub Data Platform: Lakehouse and Kafka

## Learning notification feed (2026-11)

LMS owns `learning_notification_events` and `learning_notification_reads`.
Forward migration V021 is embedded and installed before HTTP startup, in one
transaction under an advisory lock, following the existing LMS startup-schema
pattern. A complete existing schema is recognized without replaying seed events;
a partial schema stops startup rather than dropping/rebuilding data. Operators
may instead apply V021 transactionally before rollout. Deploy LMS before frontend;
the Personalize text cleanup is compatible in either order. No Auth email change
is required and no additional notification email is sent by this feature.

Database triggers capture published course, chapter and content publication,
edits, order changes and removals in the mutation's transaction. Draft/no-op/AI
index-status writes are silent. Known course publications from the last 14 days
are backfilled; historical edits are not invented. The outbox has no recipient
copies: visibility and accepted enrollment are checked when reading. The scope
function matches the catalog's organization/private-organization rules. Revoked
access, hidden content and moved resources cannot leak through old events.

An indexed relay inspects only pending rows (50 per two-second tick), claims them
with `FOR UPDATE SKIP LOCKED`, and coalesces Redis wake-ups by channel per batch.
It marks rows delivered only after publish, rolling back on failure. It never
holds up the course-edit transaction. Redis channels are `learning:course:<id>`,
`learning:org:<id>`, `learning:public` and `learning:user:<id>`. They carry only the
constant `refresh`, no resource names, IDs or personal text in the message body.
The JWT-authenticated SSE endpoint subscribes only to the viewer's scope. Browser
connections close while hidden, reconnect with capped backoff, and receive a
catch-up hint after subscribing. Connections expire after five minutes to
revalidate authentication/scope. Redis is a hint bus, not durable storage:
reconnect, visibility and bell-open reads recover missed hints from PostgreSQL.

The existing `personalize.notification.trigger` topic additionally has a
lightweight LMS hint consumer (`lms-notification-hints-v1`). Its unchanged
`user_id` payload wakes the corresponding SSE stream; repeated hints are harmless.
The consumer commits after the Redis wake-up, retries failures, and starts at the
latest offset for a new group because the durable suggestion source is read on
connect. Auth retains its separate email consumer/group. The frontend BFF reads
Personalize directly with internal authentication and enriches only alerts whose
courses are in the authenticated LMS response; no AI request or cross-service DB
read is needed.

The bell uses explicit **Học tập** and **Gợi ý** groups. Learning includes real
course/chapter/content changes and quiz deadlines; struggle/inactivity/practice
suggestions belong to Gợi ý. Course/content titles and exact content or chapter
links replace raw numeric identifiers. The chapter/content deep links also work
when the viewer is already inside the same course. An event revision in learning
links reloads a lesson that is already open so edited content does not remain
stale. Deleted resources link to the
remaining chapter/course instead of a missing item.

At most 20 change groups and five course launches are read, plus five upcoming
quiz deadlines and eight suggestions. Bulk content additions group per chapter
per ten-minute window. Repeated edits collapse to the latest event of that type
for the resource; a new edit has a new read identity. A feed read uses bounded
relational queries, not catalog/chapter crawling. The browser has no periodic
notification polling; refresh hints are debounced and concurrent reads deduplicated.
Mark-all-read is one bulk idempotent write. Server receipts and capped browser
caches/failed-write queues are scoped to the authenticated user. Initial history
does not produce a toast storm. Inaccessible resources are removed on each read.

The serving window is 30 days. Hourly cleanup removes expired events/receipts in
bounded batches of 1,000; older records may remain pending cleanup but are not
served. Purpose: notify learners of changes to accessible learning material and
provide their own study suggestions. Only resource titles/keys and read timestamps
are stored here, never lesson bodies or answer text. Existing source-event
retention and SMTP preferences are unchanged.

Regression coverage: Go notification handler/format tests, frontend
`tests/notifications.test.cjs` and `tests/notification-navigation.test.cjs`, and an
isolated PostgreSQL/WASM integration suite:

```bash
npm install --prefix /tmp/bdc-notification-pg --no-audit --no-fund @electric-sql/pglite@0.5.15
PGLITE_TEST_MODULE=/tmp/bdc-notification-pg/node_modules/@electric-sql/pglite/dist/index.js \
  node --test lms-service/tests/notification_events.mjs
```

These tests exercise real trigger/transaction/scope SQL without production data.
After rollout, verify a published content edit reaches an enrolled viewer, an
outsider sees no private update, and Redis reconnect recovers the stored event.
This is functional coverage, not a production latency/load benchmark.

## Behavioral recommendation serving (2026-11)

Roll out LMS and Personalize before Recommender, then the frontend. No Kafka
topic is renamed. Personalize creates the additive `learner_profile_snapshots`
table at startup and backfills existing learning history in its worker.
HTTP reads snapshots only; worker projections coalesce dirty user/course pairs
on a one-second tick. Profile computation and Parquet export run off the ASGI
event loop. Archived micro-interactions remain part of course-profile history.

The existing LMS learning-events and analytics producers, plus authenticated
frontend recommendation interactions, feed this projection. The internal
`/personalize/student/{id}/recommendation-profile` route requires `X-AI-Secret`.
Course metadata comes from the authorized catalogue/enrollments; the snapshot
contains per-course action counts and latest timestamps, not raw learner text.
Behavioral features use a 90-day window; source-ledger retention is unchanged.
The profile is for the learner's own recommendations and existing internal
analytics only. Event IDs remain the deduplication keys; duplicate/late input
must not multiply evidence or roll the latest action timestamp backwards.

`recommender.interactions.v1` now accepts `favorite` (explicit interest) and
`not_interested` (suppress that course for 30 days). Existing impression, click,
accept, reject, dismiss, started and completed events remain compatible. A
rejection/dismissal is a short-lived penalty, not permanent disinterest. New
tracking tokens bind the user, recommendation and entity; previously issued
tokens remain accepted during the compatible transition. Feedback is published
to Kafka before acknowledgement, with a bounded per-process cache bridging
projection delay. If publication fails, explicit feedback is not shown as saved.
The durable ledger survives recommender restarts. Behavioral snapshots are
cached for five seconds and may be served stale for up to one hour on dependency
failure; response fallback is explicit. Browser clicks are not counted as starts:
starts occur on content exposure, completions on confirmed content completion.
Attribution expires after 24 hours and tracks only its target content when known.

Discovery retrieves a general catalogue page plus up to two topic-specific
candidate pages from explicit interests/recent enrollment history. Ranking
prioritizes explicit preference and learning history; popularity/freshness are
small secondary signals. Frontend uses backend `rank`, not pre-diversity score.
Catalogue/enrollment rendering does not wait for profile/ranking. Serving has a
two-second deadline, with bounded BFF/browser waits and an explicit fallback.

Daily and chat course actions and `/v1/recommendations/next-best-lesson` share
`app/next_action.py`. LMS supplies published content in curriculum order, actual
completion, last-open activity, observed mastery and declared skill-prerequisite
eligibility. Enrollment must be accepted. Unmapped content can still be the next
lesson; missing mastery is not a skill gap. The policy prioritizes observed
remediation, resuming the most recently opened unfinished item and the next
eligible curriculum item, deduplicating content and respecting a time budget.
Links identify the exact content. Durations are baseline estimates (up to ten
minutes per item), not measured lesson times. Missing author prerequisite/skill
maps cannot be inferred by this policy. Legacy LMS personalized endpoints remain
compatible, but the current daily dashboard consumes the shared action policy.

Design references: [YouTube's two-stage recommendation paper](https://research.google.com/pubs/archive/45530.pdf)
and [YouTube's documented history and feedback signals](https://support.google.com/youtube/answer/16089387?hl=en-GB).
This release applies these serving/feedback principles to an explainable rules
baseline; it does not claim to reproduce YouTube's trained models. Validate
production latency and start/completion outcomes before claiming a quality lift.

## Scope and authority

Learning event retry contract: deploy LMS before the matching frontend. The
authenticated `POST /personalized-learning/events` accepts optional `event_id`
(up to 100 characters). LMS namespaces this key by authenticated student and
uses the existing unique event ID constraint; replays return the original event
and can retry a failed mastery refresh without adding another answer row.
Clients without a key retain server-generated IDs. JSONB metadata is sent as
JSON text (SQL NULL when absent), compatible with pgx simple protocol.
Quiz review produces one stable key per attempt/question for learner progress;
its browser marker is written only after every request succeeds. Failures leave
the attempt retryable on reopening. Existing browser markers are preserved:
older failed attempts already marked by a previous frontend need targeted
recovery, rather than clearing all markers and duplicating historical events.
Kafka projections may receive the same event ID again and must remain idempotent.

This guide documents the implementation-backed data boundary in this repository.
It covers the DuckDB Lakehouse in `personalize-service`, the topics referenced
by current producers/consumers, and the rules for extending them. Source files
named in this guide are authoritative when details differ. A topic accepted by
a consumer is not automatically proof that a producer is implemented here.

The separate [Data Warehouse](../data-warehouse/README.md) now implements the
initial BigQuery foundation, bounded real LMS Kafka capture, batch loading, and
logical staging/fact/mart/quality views. The project owner's
[billing-disabled decision](adr/2026-10-21-bigquery-billing-disabled-foundation.md)
means no streaming/DML and limited Sandbox retention. It includes
[active setup](../data-warehouse/docs/05-bigquery-setup.md) and an
[optimization playbook](../data-warehouse/docs/06-data-engineering-optimization.md).
The continuous worker and release workflow are implemented in
[`worker/`](../data-warehouse/worker/) and
[the warehouse workflow](../.github/workflows/data-warehouse-production.yml);
use the [verified production receipt](warehouse-production-status.md) and pod
status to verify the deployed revision. Historical
CDC/SCD remains planned. The initial bounded source capture uses
the existing `lms.analytics.interactions` contract without changing producers,
joining a consumer group, or committing offsets. The existing DuckDB/profile
pipeline below remains its own service-owned boundary.

The continuous worker uses its own `bdc-warehouse-lms-v1` offset group, a private
SQLite journal on a bounded PVC, stable batch-load job identities, and commits
Kafka offsets only after BigQuery acknowledgement. Short-lived projected K3s
tokens authenticate through Workload Identity Federation; the ingest identity
writes raw only, while a separate migration identity updates warehouse models.
See [continuous deployment](../data-warehouse/docs/07-continuous-deployment.md)
for replay, malformed records, expiry, quota, and rollout/rollback behavior.

The warehouse foundation now has a versioned
[source register](../data-warehouse/contracts/sources.json), an allowlisted raw
platform envelope, and conformed learning/recommendation/LLM-attempt stars.
[Implemented dimensional modelling](../data-warehouse/docs/09-dimensional-model-implementation.md)
defines each grain, key, inferred member and unknown measure. Source-owned AI
metadata snapshots use a read-only consistent export and a durable confirmed-ID
cache; the warehouse never connects to AI's PostgreSQL database. Auth login, Lab,
Chat and richer AI/agent attribution remain explicitly gated source integrations.
New data marts, dashboards, DSS, recommender/conversational-recommender changes
and model-training applications are deferred until this foundation is verified.

## Architecture

Authoring scope is resolved by LMS from chapter/lesson IDs and passed to AI over
authenticated HTTP. AI reads only its own chunk/graph index; Studio persists
lesson snapshots and the course bank stores source provenance in question
settings. No new analytics event or Kafka schema is introduced. See
[curriculum-scoped authoring](adr/2026-10-13-curriculum-scoped-authoring.md) for
ownership, privacy purpose, failure behaviour and rollout order.

```text
LMS micro-interactions  -- Kafka --> Personalize worker --> DuckDB Bronze
                                                       |        |
                                                       |        +--> Parquet archive/export
                                                       v
                                                Gold views/profile
                                                       |
                             Kafka profile update ----+----> AI worker

Recommender outcome events -- Kafka --> Personalize worker --> Bronze ledger
Personalize notifications  -- Kafka --> Auth notification consumer
```

The lakehouse is an analytics/profile boundary. LMS, Auth, Lab, and Chat remain
the systems of record for their own transactions. Do not use a Gold result to
overwrite source-of-record state without an explicit product workflow.

## Lakehouse implementation

`personalize-service/app/services/lakehouse.py` stores DuckDB state under
`DATA_DIR` (default configured by the service) in `student_analytics.duckdb`.
It writes archival/export assets to `lakehouse/bronze/` and `lakehouse/gold/`
below that directory. The worker (`app/worker/kafka_worker.py`) has one consumer
group, `personalize-worker-group`, and runs an hourly archive scheduler.

| Layer | Current assets | Purpose | Mutability |
|---|---|---|---|
| Bronze | `bronze_interactions`, `bronze_login_logs`, `bronze_clickstream`, `bronze_course_interactions`, `bronze_recommendation_events`, `bronze_user_onboarding` | Raw/near-raw operational events | Append/idempotent by event key; onboarding upserts by user |
| Derived views | `unified_interactions` and service-defined views | Normalised analytical joins/derivations | Recomputed from Bronze/current tables |
| Gold | profile, course metrics, concept struggles, alerts, interaction matrix and study recommendations | Product/analyst-ready aggregates | Derived; never manually edited |
| Export | Parquet Gold files and archived Bronze partitions | Offline analysis and reproducible extracts | Snapshot/append according to export job |

`bronze_user_onboarding` is the explicit cold-start source. It stores interested
categories, target career and experience level without assigning a fabricated
default persona. Internal clients read/write it through
`/personalize/student/{user_id}/onboarding` and `/personalize/onboarding`.
Recommender `hybrid-rules-v3` uses these fields before falling back to level,
quality-adjusted popularity, freshness and stable exploration.

Existing DA/ML notebooks live in the `da-analytics/` submodule. They should read
approved Parquet snapshots or a read-only DuckDB copy through `BDC_GOLD_DIR` or
`BDC_DUCKDB_PATH`; they must not write the live production database.

## Topic catalogue

| Topic | Producer in this repo | Consumer in this repo | Status/role |
|---|---|---|---|
| `lms.analytics.interactions` | LMS | Personalize, LMS | Implemented micro-interaction pipeline |
| `lms.document.uploaded` | LMS | AI worker | Implemented document processing command |
| `lms.ai.command` | LMS and AI worker | AI worker | Implemented async AI command/job pipeline |
| `lms.ai.interactive` | LMS | AI worker (dedicated group) | Latency-sensitive jobs a learner is waiting on, currently wrong-answer diagnosis. Separate consumer group so batch work cannot block it |
| `ai.job.status` | AI worker | LMS | Implemented AI job status pipeline |
| `ai.document.processed.status` | AI worker | LMS | Implemented document indexing status |
| `lms.graph.command` | Trigger endpoints/services | AI worker | Implemented graph command boundary |
| `ai.graph.status` | AI worker | No consumer found here | Producer exists; verify downstream before relying on it |
| `ai.graph.node_merged` | AI worker | LMS | Implemented reference-rewrite notification |
| `lms.maintenance.command` | LMS | AI worker | Implemented cleanup/maintenance command |
| `personalize.profile.updated` | Personalize | AI worker | Implemented profile update signal |
| `recommender.interactions.v1` | Recommender | Personalize | Implemented outcome ledger ingestion |
| `personalize.notification.trigger` | Personalize | Auth; LMS hint consumer | Existing email trigger plus scoped in-app refresh hint |
| `user.login.events` | No producer found here | Personalize | Consumer acceptance only; integration gap |
| `lms.analytics.telemetry` | No producer found here | Personalize | Consumer acceptance only; integration gap |
| `lms.course.interactions` | No producer found here | Personalize | Consumer acceptance only; integration gap |
| `lab.job.command`, `lab.job.status`, `lab.session.idle`, `lab.session.checkpoint` | Lab constants | Lab status consumer | Contract surface exists; verify a producer/runner before product dependence |

Coding/SQL practice grading currently uses synchronous runtime adapters, not
`lab.job.*`. Terminal exec streams similarly do not publish session lifecycle
contracts. Submission results are saved atomically in the Lab-owned database;
SQL fixtures and restricted logins live on a separate disposable PostgreSQL
instance. No Kafka payload changed in this rollout. See
[Runtime hardening](RUNTIME_HARDENING.md) for ownership, limits and rollout.


## Implemented contract shapes

### `lms.analytics.interactions`

Producer type: `lms-service/pkg/kafka/MicroInteractionEvent`. Key is the course
ID in the current LMS implementation. Consumers must treat `interaction_id` as
the idempotency key.

```json
{
  "interaction_id": 12345,
  "user_id": 81,
  "course_id": 40,
  "lesson_id": 701,
  "node_id": 55,
  "action_type": "flashcard_flip",
  "score": 1.0,
  "status": "completed",
  "created_at": "2026-07-29T09:00:00Z"
}
```

Required fields are `interaction_id`, `user_id`, `course_id`, `action_type`, and
`created_at`. `lesson_id`, `node_id`, `score`, and `status` are optional. The
personalize worker inserts with `ON CONFLICT (interaction_id) DO NOTHING`.

### `lms.ai.command` and `ai.job.status`

Use `job_id` as the correlation and idempotency reference. The LMS owns the job
request; the worker owns processing status. Consumers must accept status updates
in a safe, repeatable way.

`DIAGNOSE_ERROR` is published to `lms.ai.interactive` instead, because a student
is waiting on that answer. The worker runs a second consumer in group
`ai-worker-interactive` with bounded concurrency (`AI_INTERACTIVE_CONCURRENCY`,
default 6). Messages from one partition are serialised so offsets stay ordered,
while six partitions allow six diagnoses in parallel. `k3s/base/kafka-ai-topics-job.yaml`
creates the topic with 6 partitions and raises `lms.ai.command` to 3 on every AI
rollout. The payload shape is identical to `lms.ai.command`; only the topic and
consumer group differ.

```json
{
  "job_id": "uuid-or-stable-job-id",
  "command_type": "GENERATE_QUIZ",
  "course_id": 40,
  "payload": {},
  "created_at": "2026-07-29T09:00:00Z"
}
```

```json
{
  "job_id": "uuid-or-stable-job-id",
  "status": "completed",
  "result": {},
  "error": ""
}
```

### `recommender.interactions.v1`

Recommender validates its signed tracking token before publishing. The producer
keys events by `user_id:course_id`; Personalize uses `event_id` as its Bronze
deduplication key. The practical minimum payload is:

```json
{
  "event_id": "uuid",
  "event_time": "2026-07-29T09:00:00Z",
  "user_id": 81,
  "course_id": 40,
  "surface": "course",
  "event_type": "impression",
  "recommendation_id": "rec_uuid",
  "recommendation_set_id": "rs_uuid",
  "entity_type": "course_action",
  "entity_id": "40:continue_course",
  "rank": 1,
  "metadata": {}
}
```

## Contract and quality rules

1. Treat Kafka as at-least-once. Every consumer must be idempotent and must not
   assume global ordering across partitions.
2. Preserve existing fields and semantics. Add optional fields first; use a new
   versioned topic for a breaking change.
3. Use an event ID and ISO-8601 event time. Use a stable key that matches the
   ordering boundary.
4. Validate required fields at the producer and record invalid/dead-letter
   handling deliberately; never silently invent business identifiers.
5. Record producer, consumer group, retention/partition requirement, PII class,
   and owner in the PR. Kafka topic creation is currently permissive locally;
   production policy must be reviewed with DevOps.
6. The data team must test duplicates, late events, malformed payloads, and
   replay/backfill before using a new field in Gold or a model.

## Change and rollout procedure

1. Write the schema, compatibility decision, data purpose, and sample payload.
2. Implement consumer support for additive data first; deploy and observe it.
3. Implement and deploy the producer; verify topic, consumer lag, Bronze rows,
   and idempotent duplicate handling.
4. Add/modify derived view and Gold export only after Bronze data quality is
   demonstrated. Backfill through an explicit, reviewable job.
5. Update this guide, `da-analytics` assets if applicable, tests, metrics, and
   dashboard/alert definitions in the same delivery.
6. For a rollback, stop the producer or feature flag first. Do not delete raw
   data or rewrite a contract to hide a bad deployment; document remediation.

## Data access and privacy

- Service-to-service endpoints require their configured internal authentication;
  do not expose the Lakehouse database or internal analytics endpoints publicly.
- Analysts receive approved, read-only snapshots or access paths, never runtime
  secrets or unrestricted production shell access.
- Minimise identifiers and metadata. New personal-data fields require a purpose,
  retention/deletion policy, access owner, and BA/privacy review.
- Log counts, lag, failure and dedupe rates without logging credentials or raw
  sensitive payloads.

### Personal flashcard library

Owner: AI service. LMS authenticates `POST /api/v1/courses/:courseId/flashcard-library` and injects
`student_id` and the authorized `course_id`; AI owns `personal_flashcard_decks`, `personal_flashcards`,
`personal_flashcard_reviews`, and `personal_flashcard_jobs`. The internal API is
`POST /ai/flashcards/personal` with `X-AI-Secret`. Every read/write is scoped to both the learner and course, after LMS course-access verification.
Cards can be created manually for any subject; cards generated from a lesson keep the exact linked node IDs as source metadata. Review and scheduling do not depend on nodes.

LMS produces `PERSONAL_FLASHCARD` on the existing `lms.ai.command` topic, keyed by
job UUID, with payload `{ "job_id": "<uuid>" }`. AI worker loads the owner and input
from its own job table. This is an additive command; deploy the new worker before
the LMS producer. No learner answer or source material is placed in Kafka. Stored
input is used only for requested card generation or answer evaluation. Existing
`ai_job_status` updates carry only the job ID; private results are read through the
owner-scoped library `job` action.

Free-topic generation returns editable drafts. Explicit generation from the current accessible LMS content saves cards directly into a source-linked deck in the learner's course. LMS resolves the canonical content or micro lesson after authorizing the learner. Enrolled learners can open unpublished section content in the learning page, so generation uses that same course access rule; AI joins nodes only by the exact course/content link and reads indexed chunks for that content when needed. A missing source yields a visible error instead of invented cards. A lesson quiz returns private multiple-choice questions and does not save flashcards. Content generation sends bounded excerpts spread across the current lesson through the configured LLM gateway; a context-window rejection retries with a smaller excerpt and fewer items. Gateway usage records include the study job ID for admin diagnostics. Worker `ai.job.status` now reports `failed` when the private job fails rather than reporting a misleading completion. The worker clears the copied lesson body from completed job payloads; source links remain in the owner's deck/card and are removed when those records are deleted. Answer
checks use a stable review UUID; transaction/card locks and the review primary key
prevent a retry from advancing a schedule twice. Worker deliveries serialize on a
PostgreSQL advisory lock and reuse completed jobs. Model calls have bounded
timeouts. Queue failures and model failures are surfaced to the learner; they do
not award progress. An edited card increments its revision, so an in-flight check
cannot grade against a changed answer.

Rollout: the AI deployment step runs `scripts/apply-flashcard-migrations.py` before rollout. It adopts previously applied V016/V017 from their complete schema and applies only missing migrations, including V018 for lesson jobs/source links. Deploy AI HTTP and worker, LMS, then frontend. Run `scripts/check-flashcard-rollout.sh` after rollout to identify a missing AI route, LMS route, or schema. The migration copies active legacy cards
and their repetition schedules into each owner's `Thẻ đã lưu` deck. V017 splits
that deck by original course while preserving card IDs, edits and review schedules.
Unscoped cards created between V016 and V017 are retained; their owner can explicitly
assign their deck into an accessible course using `assign_deck`. New decks/jobs
always require a course. Legacy data
is retained for rollback; subsequent personal-library edits are not synchronized
back to the old node tables. The frontend removes node-generation entry points,
and LMS no longer registers the old generate/bulk-save routes. `generate_content` and `quiz_content` jobs use a browser UUID that is stable on retry; worker transactions atomically save cards/job results and serialize duplicate deliveries. Browser speech
uses Web Speech API voices, with explicit playback, voice selection and speed;
no new cloud TTS account or credential is required.

Validation: `FLASHCARD_TEST_DSN` may point to an isolated PostgreSQL instance to run
`tests/test_personal_flashcards.py` in AI. The integration test creates/drops a
unique schema and checks migration preservation, ownership, revision conflicts,
review idempotency and cascade deletion. Never use a production DSN for tests.

### Lab authoring drafts (AI-owned data)

`ai-service` owns `lab_authoring_jobs` (migration V019); `lab-service` remains
owner of labs, testcases and terminal grading evidence. The authenticated
NextAuth proxy injects `owner_id` into `POST /ai/lab-authoring`; reads filter by
both job ID and that owner. The HTTP endpoint queues a bounded proposal job and
returns 202 with `QUEUED/RUNNING/READY/FAILED`, proposal/error and
`apply_required=true`. It never writes lab data or runs generated code.

The dedicated `app.worker.lab_authoring_worker` polls this durable table without
Kafka, embeddings, Qdrant or Neo4j dependencies. Claims use `FOR UPDATE SKIP
LOCKED`, a unique lease token and a four-minute lease. Generation is bounded to
180 seconds; interrupted leases can recover up to three claims, and completion
requires the same token. Failed drafts require a teacher retry. Completed and
failed rows expire after seven days; source text and reference code are private
authoring data and are not emitted to learner APIs or the Lakehouse.

Gateway tasks are `format_lab`, `create_lab`, `create_lab_testcase`,
`edit_testcase`, and `create_lab_generator`. Each has an independently editable
model binding and existing gateway fallback/key quota handling. No new Kafka
contract is introduced. A preview is applied only through normal permission-
checked Lab APIs. Code generators and reference solutions run through the
restricted coding adapter; they are never executed by AI/API Python processes.

Rollout: migrate V019 with the existing AI migration runner, roll out AI HTTP
and its lab authoring worker under the same immutable image, then deploy Lab
API and frontend. The production script now selects the authoring worker with
other AI workloads. Rollback can retain V019 and its private drafts; it must
never reinterpret drafts as published labs. This describes code/configuration,
not evidence of a production rollout.

## Knowledge Farm rewards

Farm learning attempts are a separate asynchronous HTTP outbox contract.
Farm owns `game_learning_outbox`; LMS owns `farm_learning_attempts`,
`micro_lesson_interactions` and `knowledge_node_mastery`. Each completed
challenge, including incorrect answers, is sent to LMS
`POST /api/v1/internal/farm/attempt` with `challenge_id` as the stable
idempotency key, authenticated by the existing `AI_SERVICE_SECRET`. The payload
contains only the learner ID, course/node IDs, LMS source ID, question kind and
correctness; it contains no answer text. LMS commits raw interaction and
mastery update together. A missing node remains in the course interaction log
but cannot update a node heatmap. Farm retries until LMS acknowledges 204.
This is for learning analytics; Auth score still uses the reward topic below.
Deploy LMS V019 and endpoint before Farm V003/outbox producer. Internal
credentials stay server-side and a learner's JWT is never stored in the outbox.

Owner: Farm producer / Auth consumer. Topic: `farm.harvest.reward.v1`, key:
base-10 Auth user ID, 3 partitions, 30-day retention in supplied topic setup.
Purpose: credit learning-game harvest rewards to the canonical
`users.total_score`; no automatic Lakehouse ingestion or LMS progress update.

Payload v1: `version:1`, UUID `event_id`, UUID `harvest_id` (same as event ID),
positive integer `user_id`, `delta:5`, RFC3339 `occurred_at`, hex `signature`.
HMAC-SHA256 input is the UTF-8 string
`event_id|user_id|harvest_id|delta|occurred_at|1`, signed using FARM_EVENT_SECRET.
Unknown additive fields are ignored; a changed semantic contract needs a new
version/topic. The cross-language fixture is in
`auth-and-management-service/src/test/resources/farm-reward-v1.json`.

Farm commits state + answer result + outbox atomically. Auth consumer group
`auth-farm-rewards-v1` validates payload/signature and inserts
`farm_score_receipts` plus an atomic score increment in one transaction;
unique event and harvest IDs prevent double credit across replay and replicas.
Broker errors retain the outbox. Consumer errors roll back and retry without
committing offsets; malformed events stop the partition for operator repair.
Only IDs, score delta and timestamp are transmitted, never quiz responses,
email, JWT or a complete user profile. Retain inbox for the replay lifetime.

Roll out Auth schema and consumer before Farm producer and frontend. Rollback
must preserve ledger and outbox; do not delete receipts to reverse a release.
Full [feature, rollout, replay and key-rotation guide](features/KNOWLEDGE_FARM.md).

## Studio media and speech jobs

`studio_projects`, `studio_jobs` (V020) and `speech_jobs` (V021) are owned exclusively
by AI. The authenticated frontend BFF submits owner-scoped requests; AI HTTP creates
leased jobs and the existing AI worker polls them. Studio stores source snapshots,
plans, provenance and artifact references. Speech reads only the learner's owned
flashcard and course, then caches its narration. V022 Studio artifacts use a
private unversioned MinIO bucket with owner/course download checks. Video MP4,
narration and ZIP expire 600 seconds after ready; source HTML/storyboard/PDF
persist. Flashcard speech caches retain the separate `studio/speech/` policy. No LMS or Auth
database is accessed by this implementation and no Kafka payload/topic changes.

Leases and input-hashed checkpoints support duplicate submission, worker recovery
and safe retries. A stale worker cannot overwrite a newer job. Storage/provider/QA
failures leave a visible failed project; no partial MP4 is marked ready. Consumer
rollout is migrations and AI worker before AI HTTP/frontend. Old images should drain
jobs before rollback; retain forward tables. See [content authoring pipeline](CONTENT_AUTHORING_PIPELINE.md)
for retention, cleanup retries, encrypted shared YouTube credentials and rollback limits.

Own-model MCP authoring adds no text-model generation or new Kafka contract.
`mcp_authoring_requests` atomically deduplicates personal card/project creation.
Media manifests outlive project deletion so cleanup can recover. Independent
worker loops delete expired media and resume shared-channel YouTube uploads;
the frontend bridge owns Google OAuth communication. Completed course videos
retain only processed YouTube links and authoring provenance. Publication uses
the authenticated LMS content API and reconciles project metadata on retries.
# Learner notebook annotations (2026-11-05)

Notebook entries remain user-owned records in Personalize's DuckDB
`notebook_entries`; the optional `annotation` TEXT column contains version-1 JSON
for student text highlights: `content_id`, exact `quote`, nearby `prefix/suffix`,
UTF-16 `start/end` offsets and one of yellow/green/blue/pink. This is personal
learning data, not a new analytics event or Kafka topic. The browser produces
annotations only on explicit save; BFF injects authenticated user identity,
AI proxies the additive field, and Personalize validates it and applies the
existing owner-scoped list/update/delete rules. The field is never a grant of
course/lesson access. Existing LMS authorization still controls lesson reads.

Purpose: restore private learner highlights and open their associated notebook
comments. Retention/access match existing notebooks: owner-only through the
authenticated proxy, internal service-secret authentication between services;
deleting a note removes its live annotation, and explicitly setting annotation
to null removes only the highlight. Existing backup policies are unchanged.
No new public endpoint, automatic telemetry or separate export is introduced.
Legacy PUT callers that omit annotation preserve the stored value.

Personalize applies the additive/idempotent migration under its DuckDB lock at
startup; see `personalize-service/migrations/V20261105__notebook_annotations.sql`.
Rollout order: Personalize → AI HTTP → frontend. Old notes require no backfill.
Do not run tests against a production DuckDB file; tests force a temporary data
directory and verify legacy rows, isolation, color updates and removal.

### Quiz insights command

LMS produces `ANALYZE_QUIZ_RESULTS` on existing `lms.ai.command`, keyed by the
stable `job_id` (`quiz-insights-<uuid>`). AI worker consumes it using the dedicated
`quiz_insights` LLM task and publishes existing `ai.job.status` statuses/results.
LMS owns authorization and snapshots; AI owns interpretation. This additive command
does not change existing consumers or create a new topic. Deploy AI V024 and its
worker before enabling the LMS/UI producer; older workers reject an unknown command.

Payload fields are `summary` (whole-quiz counts, score and focus/time aggregates),
`distribution` (five score bins), and `questions` (question statistics/options).
The size is independent of the number of learners/attempts. `unique_students`
counts everyone who started; `submitted_attempts` counts submitted attempts.
No student names, student IDs, individual scores/answers, IP addresses or browser
agents are sent. The worker still accepts the initial `scores` payload for
in-flight command compatibility. A shared LMS Redis SET NX gate reuses a quiz's
analysis job for five minutes, bounding duplicate creation across replicas.
The purpose is teaching feedback: observed question difficulty, topics needing
reinforcement and limitations of the evidence. Visibility cannot establish cheating.
The AI response contains `summary`, `strengths`, `gaps`, `recommendations` and
`limitations`; LMS returns it only after reauthorizing the course and quiz/job scope.

At-least-once retries use an AI PostgreSQL transaction advisory lock and the
`quiz_insight_results.job_id` primary key. Completed duplicate deliveries reuse the
saved result; failures roll back and release the lock, allowing redelivery. Model
calls time out after 150 seconds; failure is published as `failed`. LMS pending
state and job scope expire after 24 hours. AI prunes saved results older than 24
hours on subsequent analysis processing. Queue failure returns 503; no result is
presented as completed. Rollback the producer/UI first when removing worker support.
