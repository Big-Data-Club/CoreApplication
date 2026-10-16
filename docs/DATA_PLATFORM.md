# BDC Hub Data Platform: Lakehouse and Kafka

## Scope and authority

This guide documents the implementation-backed data boundary in this repository.
It covers the DuckDB Lakehouse in `personalize-service`, the topics referenced
by current producers/consumers, and the rules for extending them. Source files
named in this guide are authoritative when details differ. A topic accepted by
a consumer is not automatically proof that a producer is implemented here.

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
| `ai.job.status` | AI worker | LMS | Implemented AI job status pipeline |
| `ai.document.processed.status` | AI worker | LMS | Implemented document indexing status |
| `lms.graph.command` | Trigger endpoints/services | AI worker | Implemented graph command boundary |
| `ai.graph.status` | AI worker | No consumer found here | Producer exists; verify downstream before relying on it |
| `ai.graph.node_merged` | AI worker | LMS | Implemented reference-rewrite notification |
| `lms.maintenance.command` | LMS | AI worker | Implemented cleanup/maintenance command |
| `personalize.profile.updated` | Personalize | AI worker | Implemented profile update signal |
| `recommender.interactions.v1` | Recommender | Personalize | Implemented outcome ledger ingestion |
| `personalize.notification.trigger` | Personalize | Auth | Implemented notification trigger |
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
