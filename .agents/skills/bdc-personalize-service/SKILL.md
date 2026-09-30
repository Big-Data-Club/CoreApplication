---
name: bdc-personalize-service
description: Personalize service guidance for DuckDB Lakehouse ingestion, learner profiles, alerts, Parquet export, and Kafka data contracts.
triggers: [personalize-service, duckdb, lakehouse, bronze, gold, learner-profile, analytics]
version: "3.0"
requires: [bdc-core-orchestrator]
---

# BDC Personalize Service

## Scope

`personalize-service/app/services/lakehouse.py` owns DuckDB tables, views,
exports, and ingestion behaviour. `app/worker/kafka_worker.py` consumes
analytics/recommendation inputs, derives profiles, archives data, and publishes
profile/notification signals. `app/api/` exposes internal analytics/profile
routes.

## Rules

- Bronze is append/idempotent ingestion; Gold is derived. Never hand-edit Gold
  to correct a product result. Correct the source event/derivation and use an
  explicit backfill if needed.
- Preserve event IDs and current dedupe keys. Handle duplicates, late events,
  malformed payloads, lock/concurrency safety, and disk growth explicitly.
- Internal Lakehouse/profile routes require internal authentication and must not
  become public browser endpoints or expose raw personal data.
- New fields require data purpose, retention/access decision, producer/consumer
  contract, quality checks, and Data Platform documentation.
- Treat `user.login.events`, `lms.analytics.telemetry`, and
  `lms.course.interactions` as consumer-only integration gaps until an in-repo
  producer and end-to-end test exist.
- Add pytest coverage and use read-only snapshots for analyst work. Never point
  offline notebooks at a live production DuckDB write path.
