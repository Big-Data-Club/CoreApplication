# Verified warehouse production release

Observed: 2026-10-21, approximately 17:59 UTC. This is a deployment receipt;
recheck live metadata before relying on it after configuration or retention changes.

## Release and runtime

- CoreApplication revision: `30e7d7a499fd560668c7773fcecb21cfc5d48e57`.
- Warehouse source pin: `8048312`.
- [Production CI/CD run](https://github.com/Big-Data-Club/CoreApplication/actions/runs/39647466315):
  verification, image build, and deployment all succeeded.
- Immutable image digest:
  `sha256:9b1a35d3ea9cd8706739064322ebcb717fe5abb47624f9645c642f38324be682`.
- Deployment `default/data-warehouse-worker`: one ready replica on the expected
  revision. The new pod had zero restarts in the observed rollout.
- Both raw-model and view migrations succeeded under the dataset-scoped deployment
  identity. Dataset bootstrap is separate from runtime migrations.
- The ingest identity uses short-lived Workload Identity Federation credentials.
  No service account private key or human Google login was installed in the pod.

This receipt supersedes the continuous-ingestion status in the older
[initial-load snapshot](../data-warehouse/docs/deployment-status.md).

## Actual source-to-warehouse evidence

The worker acknowledged a batch of 205 real records from
`lms.analytics.interactions`, partition 0. No artificial events were published.

- Load job:
  `bdc_worker_2dc18dd61faa4ed50abcf2f0e2b7f69ffe0a8ffa769bdd6e99057f80beb17c2e`.
- Last acknowledgement: `2026-10-21T17:58:12.993273Z`.
- Kafka group `bdc-warehouse-lms-v1`: committed offset 4023, broker end offset
  4023, lag 0. Inspection did not read source records or commit offsets.
- Worker status: ready, one successful batch, 205 acknowledged rows, zero pending
  records, no reported error.
- Reconciliation job: `bdc_dw_dee3247fb16c4b829225acb0c4310beb`.

| Reconciliation | Observed result |
|---|---:|
| Raw deliveries for the captured source coordinates | 410 |
| Distinct acknowledged source coordinates | 205 |
| Payload hash mismatches | 0 |
| Distinct fact events | 205 |
| Identity conflicts | 0 |
| Sum of daily mart interactions | 205 |

Raw deliveries include the original one-shot load and the continuous group's
legitimate replay of retained source events. Stable event identity and payload
hash deduplication keep fact/mart counts at 205. This demonstrates a successful
real batch and reconciled replay; a live pod/node restart recovery exercise was
not performed. Crash-window recovery is covered by isolated tests.

## Operating boundaries

Batch flush interval is 300 seconds, bounded by 1,000 records/1 MiB. The worker
continues consuming new real events and commits Kafka offsets only after an
acknowledged BigQuery load. The project remains in the selected billing-disabled
mode. Raw-table expiry observed at `2026-12-20T15:10:44.388Z` still applies;
this deployment does not establish permanent history or recover events outside
Kafka retention.

See the [deployment guide](../data-warehouse/docs/07-continuous-deployment.md)
for checkpoint, quota, privacy, and expiry behavior, and the
[DevOps runbook](teams/DEVOPS_RUNBOOK.md) for release recovery. The release includes
16 warehouse tests and six parent deployment/selection tests. Runtime inspection
and reconciliation emitted operational metadata/counts only, never source rows.
