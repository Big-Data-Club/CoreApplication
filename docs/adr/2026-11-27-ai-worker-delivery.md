# AI worker delivery, recovery and lane isolation

Status: accepted for implementation; production capacity is not benchmarked.

## Problem

A malformed consolidation completion escaped the shared batch consumer and
terminated both batch and interactive lanes. Quiz work had no automatic sweep
for a lost enqueue notification or expired claim. Interactive finally-block
commits could acknowledge cancelled or failed work.

## Decision

Keep the existing batch and interactive topic/group identities and offsets.
Add `lms.ai.memory.v1` (3 partitions, group `ai-worker-memory-v1`) and run three
separate deployments sharing one image: batch `ai-worker`,
`ai-interactive-worker`, and `ai-memory-worker`. Initial execution limits are
1 batch record, 2 interactive records, and 1 memory record per process. These
are conservative limits, not measured capacity. Native embedding/reranker
loads and inference are serialized within each process to avoid cold-load races.
Light lanes join Kafka without eager model initialization; embedding remains
lazy when their actual work needs it. They share disk model cache, not RAM.

Use one task per assigned partition, pause that partition while its record is
in flight, and cap active handler execution. Completed handlers waiting for
commit/quarantine release their execution slot while retaining their partition
pause; memory remains bounded to one record per assigned partition. Commit only `{partition: offset+1}`
after handler success or an acknowledged quarantine write. Retries are bounded
(3 attempts with backoff); invalid envelopes go directly to quarantine. Commit
outages retry only the commit, not completed side effects. Rebalance revocation
fences and cancels old tasks; shutdown drains for at most 25 seconds before
cancelling without acknowledgement. Delivery remains at least once, so domain
idempotency remains mandatory. This is not a claim of exactly-once processing.

`ai.worker.failed.v1` stores private original envelopes with stable source
coordinates and typed errors; raw payloads/errors are not logged. Retain for
7 days and target 64 MiB/partition (3 partitions), with 8 MiB segments. Kafka retention
is segment-based and asynchronous, so the active segment/deletion delay can
exceed that target. No automatic replay: an
operator must verify the cause and domain idempotency first. Apply the same
broker access restrictions as the private source topics; Kafka base64 encoding
is not encryption. A DLQ outage pauses only the affected partition within that
lane, never commits the source, and remains observable in logs.

The old batch topic forwards legacy `CONSOLIDATE_SESSION` envelopes to the new
memory topic with the same job/session identity. Source commits follow the
forward's acknowledgement. A crash between forwarding and commit may duplicate
the envelope; persisted memory cursors and episode identities handle replay.
New HTTP producers publish directly to the new memory topic.

## Quiz recovery

Apply additive V027 before new code. Each claim increments a durable attempt
counter (maximum 3), creates a fresh claim/generation UUID, and refreshes its
3-minute lease every 30 seconds and on progress. A background sweep every
30 seconds examines at most 10 pending/expired/retryable failed jobs and shares
a process lock with Kafka quiz execution. Concurrent processes still require
an atomic database claim. Ready and terminally failed jobs are not automatically
reindexed. Retryable failures back off 60 seconds; permission/source changes
and invalid data fail terminally. Explicit authorized UI retry starts a new
job and resets attempts. Crash recovery consumes an attempt as well.

Generation UUIDs differ from stable job IDs: an expired worker can write only
its invisible generation. Publishing ready requires both current job and claim.
Readers use only the published generation. Automatic recovery reloads the
persisted requester and rechecks current LMS access on each source fetch.

## Deployment and rollback

Provision topics and quarantine retention, apply V027, then deploy memory,
interactive, batch, and HTTP in that order. Worker startup/readiness require a
running consumer loop; liveness checks event-loop responsiveness. Consumer
startup is no longer inferred from a Running container. Keep source offsets.

Old HTTP producers are compatible with the forwarding batch. After new HTTP
producers are enabled, do not remove memory consumers or roll them back to an
image without memory mode. A full rollback must first switch producers to a
compatible release, drain the memory topic, and preserve additive SQL. The
deployment helper restores complete previous Deployment specs on automatic
rollback, including mode/probes. Manual rollback to an arbitrary pre-transition
image still requires the producer/drain procedure; prefer a compatible image. Recreate strategy
bounds RAM at the cost of temporary per-lane downtime during deployment.

## Verification

Unit regressions cover per-partition ordering/concurrency, cancellation,
revocation fencing, bounded retry, quarantine failure and commit failure.
Disposable PostgreSQL verifies SQL replay, claim exclusion, retries and generation
publication. Broker integration must verify restart/rebalance on Kafka 3.7.
Production acceptance additionally requires active members in all three groups,
old/new topic backlog draining, stable restart counts and completed quiz state.
