---
name: bdc-data-engineering
description: Design, implement, review, and optimize BDC analytical pipelines and BigQuery warehouses, including event ingestion, dimensional models, CDC, replay, data quality, and cost. Use for data engineering work; use the Personalize skill for changes confined to its DuckDB profile runtime.
---

# BDC Data Engineering

Use the existing BDC warehouse architecture as the starting point. Produce a
reviewable design or implementation matching the request; editing documentation
does not authorize provisioning GCP, changing source databases, enabling CDC,
or deploying workloads.

## Repository context and reference routing

Read [BDC core guidance](../bdc-core-orchestrator/SKILL.md) for shared boundaries.
The [warehouse README](../../../data-warehouse/README.md) states current implementation
status. Read the [active billing-disabled decision](../../../docs/adr/2026-10-21-bigquery-billing-disabled-foundation.md)
for the selected project: real-event batch loads and logical views, without
streaming/DML or permanent history. Reinspect code/configuration and live metadata
before claiming a component is deployed or a resource has expired.

Read only references needed for the task:

- Platform choice or IAM/cost boundaries:
  [ADR-001](../../../data-warehouse/docs/01-tech-stack-decision.md).
- Events, outbox, Kafka sink, CDC, watermarks, failure handling:
  [pipeline design](../../../data-warehouse/docs/02-etl-cdc-pipeline.md).
- Fact grain, dimensions, SCD, attribution, metrics:
  [modelling](../../../data-warehouse/docs/03-data-warehouse-modelling.md).
- Source availability, sizing, sequencing, production gates:
  [coverage and roadmap](../../../data-warehouse/docs/04-source-coverage-capacity-roadmap.md).
- BigQuery project, credentials, datasets, actual source capture, and recovery:
  [setup](../../../data-warehouse/docs/05-bigquery-setup.md).
- Throughput, SQL plans, scan/storage cost, backfill performance:
  [optimization playbook](../../../data-warehouse/docs/06-data-engineering-optimization.md).
- Current topic producers/consumers and DuckDB/Parquet ownership:
  [Data Platform](../../../docs/DATA_PLATFORM.md). Load the
  [Personalize skill](../bdc-personalize-service/SKILL.md) when changing that service.

Keep durable technical explanations in those canonical documents rather than
copying them into this skill. Verify current provider behavior, pricing, quotas,
and SDK/CLI syntax against official sources when they affect the task.

## Establish the design contract

Identify the business question and metric owner before selecting tools. Inspect
source publishers, schemas/migrations, consumer configuration, deployment settings,
and existing tests. A topic constant or accepted consumer schema is not proof of
an implemented producer. Ask only for inputs that cannot be inferred; continue
independent design work while documenting unresolved production inputs.

For each source/target, make these decisions explicit at the useful level of detail:

- Owner, business meaning, exact row grain, natural key, event/change identity.
- Event time, ingestion time, authoritative source ordering, delete semantics.
- Capture method, topic key, consumer group, schema compatibility, replay source.
- Layer/model, history policy, metric additivity, reporting timezone, attribution.
- Freshness/recovery target, measured volume/skew, retention, privacy/access purpose.
- Quality/reconciliation gates, failure behavior, rollout, and correction path.

Prefer a small complete slice over onboarding every table. Existing LMS
micro-interactions and recommendation outcomes are the Phase 1 starting point.
The current project owner selected billing disabled and real source data only.
Do not enable billing, seed sample rows, or claim that Sandbox supports permanent
retention, streaming, or SCD2 mutations. Apply CDC in Phase 3 after source-owner and capacity work; do not introduce it as
an automatic dependency of warehouse setup.

## Design and implement pipelines

Choose domain events for semantic activity, outbox for reliable publication of
committed mutations, source-owned exports for snapshots/reconciliation, and
selective CDC for row history not captured adequately elsewhere. Keep operational
migrations in the owning service. Warehouse/analyst code must not directly query
another service's database; an explicit CDC/export integration belongs to its owner.

For new Kafka ingestion:

- Use a warehouse-specific consumer group and preserve stable source event IDs.
  Existing LMS interaction IDs need a namespace; recommendation event IDs are retained.
- Bound buffers by bytes/count/age and limit in-flight batches. Choose batch load
  or Storage Write API from freshness, volume, quotas, and replay behavior.
- Advance only contiguous durably acknowledged offsets per partition, including
  durable quarantine handoffs. Handle rebalance and shutdown without skipping work.
- Keep canonical raw evidence after privacy filtering. Deduplicate identical
  deliveries; quarantine conflicting payloads under the same immutable event key.
- Treat Kafka-to-BigQuery as at least once. Producer idempotence does not remove
  the publish/mark or write/commit crash windows. State exactly where any stronger
  guarantee applies, including stream offsets/load-job identity where used.
- Track ingest and transform progress separately. Discover new arrivals by ingestion
  time, update affected event partitions/keys, and route data outside the normal
  lookback to correction. A 48-hour event-time filter alone loses old arrivals.
- Define a replay deadline from remaining retention and measured drain capacity.
  Quota failure or a cost stop must not silently discard core events.

CDC proposals include snapshot boundaries, allowlisted columns/tables, slot/WAL
monitoring, schema history/offset durability, hard deletes, and resnapshot behavior.
A compacted current-state topic is insufficient when every intermediate SCD change
must be preserved. Stopping a connector does not release retained WAL.

## Design warehouse models

Use raw -> staging -> core -> mart. Define fact grain and measure additivity
before schema. Keep conformed entities shared, facts at their business grains,
and marts aligned to metric contracts. Aggregate facts before joining different
one-to-many processes; prevent fan-out in usage/cost attribution.

Select Type 1, Type 2, snapshots, or bridges according to historical questions.
Use canonical deterministic keys scoped by source/tenant. Reconstruct affected
historical SCD timelines for late updates; check interval overlap/current-row
uniqueness and rebind affected facts. Keep unresolved natural keys for late binding
and distinguish unknown from not applicable. BigQuery does not enforce key integrity.

For AI, one provider attempt is one cost fact; one user action can have many
attempts. Preserve effective price/currency and usage status. Unknown usage is
not zero; local inference's zero API spend is not zero compute cost. MCP telemetry
attributes the channel while domain facts count the business mutation.

Keep restricted content and secrets out before landing; raw append-only policy
does not override retention or erasure. Deletion handling must prevent backfills
and replay from reintroducing erased data.

## Optimize from evidence

Read the optimization playbook for techniques and failure cases. First identify
whether the bottleneck is source queries, serialization/network, Kafka disk/skew,
destination writes, transformations, or dashboard scans. Record a representative
baseline and preserve result semantics while changing a material variable.

Prioritize applicable changes:

- Throughput: bounded micro-batches, compression, file coalescing, partition-aware
  concurrency, backpressure, hot-key analysis, and catch-up capacity.
- SQL: projection, typed staging, source/target partition pruning, selective
  clustering, incremental keys/partitions, preaggregation, and reusable intermediates.
- Storage: layer expiration, history churn reduction, approved telemetry aggregation,
  archive lifecycle, and avoiding unnecessary duplicate retained layers.
- Cost: dry runs, per-job byte limits, query quotas, labels, and measured forecasts.
  Budget alerts are not hard spending caps; batch job creation can also allow queries.

Approximation/sampling requires an explicit accuracy/metric contract. Do not
sample committed business/cost events or shorten history merely to make a
benchmark pass. Do not add a distributed framework, indexes, partitions, or
materialized views without a workload that justifies the operating cost.

## Validate and hand off

Scale deliverables to the request: a design decision needs rationale and unresolved
inputs; implementation also needs migrations/contracts, rollout/recovery, and tests.
For data changes, cover duplicate replay, late/out-of-order changes, facts before
dimensions, partial batches, poison records, quota failure, rebalance, source deletes,
and privacy erasure as relevant. Reconcile rows and measures with the source,
accounting for filtering, rejects, duplicates, and pending late data.

For optimizations, compare equivalent outputs on the same input and report measured
bytes, latency, throughput, resources, and recovery trade-offs. Do not label
proposed values as benchmarks or claim unrun cloud checks passed. Update the
warehouse docs and Data Platform guide when their boundaries change. Verify changed
links and run `git diff --check`; run affected service/contract tests when code changes.
