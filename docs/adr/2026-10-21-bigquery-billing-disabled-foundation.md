# BigQuery foundation with billing disabled

- Status: Accepted for the initial live-data slice
- Date: 2026-10-21
- Owner: BDC Hub platform/data team
- Scope: project `bdc-web-487000`, Singapore, actual LMS analytics events

## Decision and authority

The project owner explicitly selected billing-disabled BigQuery and required real
source data only. This supersedes the billing-enabled assumption of
[warehouse ADR-001](../../data-warehouse/docs/01-tech-stack-decision.md) for the
current project. Billing will not be enabled or linked by this implementation.

Implement a bounded initial slice with local-file batch load jobs, a typed raw
LMS table, and logical staging/core/mart/quality views. Use original source IDs,
Kafka coordinates, and event times. Do not seed sample rows or invent user/course
dimensions. Runtime Google credentials and source captures remain outside Git.

## Constraints

[BigQuery Sandbox](https://docs.cloud.google.com/bigquery/docs/sandbox) does not
support streaming, DML, or Data Transfer Service. Resources expire after sixty
days; this is not durable long-term history. Logical views deduplicate retained
source deliveries and exclude conflicting immutable identities. They do not
implement persisted SCD2 or a continuous ingestion daemon.

The first capture reads only `lms.analytics.interactions` through the existing
Personalize runtime, without a consumer group or Kafka commits. LMS publishes
these events after its own database write with best-effort error handling;
warehouse completeness cannot be stronger than that source contract. No new
access to another service's database is introduced.

## Rollout and recovery

Create raw storage before views and load only validated actual source captures.
Retain immutable captures until BigQuery acknowledges the deterministic load-job
ID. Compare actual source/capture/load/fact/mart counts without exposing learner
records. A repeated invocation for the same file reuses its successful load job.

For rollback, stop new captures/loads and restore the previous compatible views;
retain raw evidence. Inspect dataset location, job state, and expiry before any
recreation. Expired history requires approved source replay/export, not a DDL rerun.
Automatic scheduling, runtime identities, durable recovery, and source-owned
historical reconciliation are subsequent deliverables.

## Implementation references

- [Active setup](../../data-warehouse/docs/05-bigquery-setup.md)
- [Foundation DDL](../../data-warehouse/ddl/001_foundation.sql)
- [Logical models](../../data-warehouse/transforms/001_lms_views.sql)
- [Deployment CLI](../../data-warehouse/scripts/warehouse.py)
- [Kafka capture](../../data-warehouse/scripts/export_lms_kafka.py)
- [Batch loader](../../data-warehouse/scripts/load_lms_batch.py)
