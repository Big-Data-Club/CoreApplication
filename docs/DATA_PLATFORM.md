# BDC Hub Data Platform: Lakehouse and Kafka

## Scope and authority

This guide documents the implementation-backed data boundary in this repository.
It covers the DuckDB Lakehouse in `personalize-service`, the topics referenced
by current producers/consumers, and the rules for extending them. Source files
named in this guide are authoritative when details differ. A topic accepted by
a consumer is not automatically proof that a producer is implemented here.

## Architecture

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
