# Verified warehouse production release

Observed: 2026-10-22, approximately 16:30 UTC. This is a deployment receipt;
recheck live metadata before relying on it after configuration or retention changes.
Only operational metadata and aggregate counts were inspected; no source rows or
credentials are included here.

## Release and runtime

- CoreApplication runtime revision: `e62003baaa2f6cf5c2212ee246adbbd0c3ea3c6e`.
- Warehouse source pin: `0e5f36d`.
- [Warehouse CI/CD run](https://github.com/Big-Data-Club/CoreApplication/actions/runs/39809991710):
  verification, immutable image build, schema migration and deployment succeeded.
- Immutable image digest:
  `sha256:e661d121da45d2b7191ee00665e10f1ca907af8d5ef28e7068fd96c03e3b4e18`.
- [AI owner-export deployment](https://github.com/Big-Data-Club/CoreApplication/actions/runs/39808779956)
  succeeded before enabling snapshot collection.
- Deployment `default/data-warehouse-worker`: one ready replica, expected revision,
  zero observed restarts, no pending records and no reported error.
- Short-lived Workload Identity Federation credentials are used by separate ingest
  and schema-deployment identities. No service account private key or human Google
  login is installed in a workload.

The cold-start pacing correction permits the first upload immediately; subsequent
uploads retain the minimum 60-second spacing. The regression test supplies a
monotonic clock of five seconds, reproducing a freshly booted runner without
increasing the test timeout. All 32 warehouse tests passed locally and in CI.

This receipt supersedes the continuous-ingestion status in the older
[initial-load snapshot](../data-warehouse/docs/deployment-status.md).

## Actual collection and reconciliation

No artificial events were published. The platform worker consumes the LMS and
recommendation topics with the separate group `bdc-warehouse-platform-v1`.

| Source | Retained distinct core events | Observed collection |
|---|---:|---|
| LMS interaction | 213 | Continuous Kafka ingestion; one partition |
| Recommendation event | 0 | Topic available with three partitions; no retained events observed |
| AI provider attempt | 63 | Authenticated source-owned snapshot; one row per recorded attempt |

The acknowledged platform Kafka load contained 213 real LMS events:
`bdc_worker_35563222d7ce55cb38cf9e1355e42e56531e5ce2af129c1608c45dffb0c732f2`.
Last acknowledgement was `2026-10-22T16:07:16.748122Z`. LMS committed/end offsets
were both 4031; all three recommendation partitions had end offset zero and no
committed offset. Total source lag was zero. Inspection did not consume source
records or change checkpoints.

The combined retained LMS evidence contains 631 deliveries across legacy and new
raw tables, resolving to 213 distinct facts. Legitimate replay does not multiply
core events. Identity-conflict checks returned zero.

AI snapshot Jobs demonstrated collection and deduplication against the real owner:

| Job | Source snapshot rows | New rows acknowledged | Unchanged rows skipped |
|---|---:|---:|---:|
| `warehouse-ai-verify-dddacb` | 45 | 45 | 0 |
| `warehouse-ai-verify-047ad9` | 63 | 18 | 45 |

Both Jobs completed successfully. The second snapshot preserved the 45 confirmed
identities and collected 18 actual new attempts. Six of the 63 attempts have
unknown usage; their token usage stays null rather than becoming a false zero.
Actor/course attribution and historical cost remain unavailable in this source.
This is metadata collection, not a prompt/response or training-content export.

Final aggregate analysis passed all 26 integrity checks: fact/dimension key
uniqueness, identity conflicts, foreign-key coverage, future timestamps, unknown
usage semantics and legacy fact compatibility. Evidence query jobs:

- Source coverage: `bdc_dw_dcc9eb1d07614015a66af1f2b4971c99`.
- Integrity: `bdc_dw_fca65923642547669719ccbe37d90a20`.
- Fact counts: `bdc_dw_28fdef79f18b4e5e8179b7443dba923d`.

These observations demonstrate real collection and repeat-snapshot deduplication.
A live node/PVC-loss recovery exercise was not performed; journal crash-window
recovery is covered by isolated tests.

## Implemented model and operating boundaries

The foundation provides raw evidence, deduplicated staging, three business facts
and six shared dimensions as logical BigQuery views. User/course dimensions are
inferred members; authoritative descriptions and SCD2 history are not claimed.
The existing learning mart remains compatible. New marts, dashboards, recommender
and conversational recommender serving, DSS workflows and model training remain
deferred.

Canonical English documentation:

- [Foundation and source contracts](../data-warehouse/docs/08-foundation-design.md).
- [Implemented dimensional model](../data-warehouse/docs/09-dimensional-model-implementation.md).
- [Target modelling catalog](../data-warehouse/docs/03-data-warehouse-modelling.md).
- [Executable source register](../data-warehouse/contracts/sources.json).

Kafka batches are bounded by 1,000 records/1 MiB with a 300-second flush interval.
Offsets advance only after a durably acknowledged BigQuery load. The AI CronJob
runs at `17 */6 * * *` UTC with overlapping execution forbidden, a seven-day owner
window, and limits of 10,000 rows/16 MiB. Interrupted capture must recover within
that available source window; the schedule is not proof of complete history.

Billing remains disabled. Metadata verification confirmed all five datasets and
19 expected table/view resources in `asia-southeast1`; the existing mart dry run
succeeded. The new raw table expires at `2026-12-21T15:23:16.831Z`. The legacy raw
table expires earlier, at `2026-12-20T15:10:44.388Z`, and is still a dependency of
the combined learning views. The earlier date therefore limits the current
learning model even if the new raw table remains available. This deployment does
not establish permanent history or automated archival.

Login, full agent/tool provenance, Lab, Chat, derived profiles and service metrics
are not yet onboarded. Missing evidence must not appear as zero business activity.
Current LMS/recommendation publishers also have documented reliability gaps;
warehouse acknowledgements do not repair events never published by a source.

See the [deployment guide](../data-warehouse/docs/07-continuous-deployment.md)
for checkpoint, quota, privacy and expiry behavior, and the
[DevOps runbook](teams/DEVOPS_RUNBOOK.md) for release recovery.
