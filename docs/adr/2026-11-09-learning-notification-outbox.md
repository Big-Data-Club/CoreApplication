# Learning notifications from a transactional LMS outbox

Status: accepted for implementation; production rollout pending.

The bell previously inferred content changes by crawling courses, chapters and
content at request time. That was incomplete, expensive and mixed actual course
updates with study suggestions. Personalize remains the owner of suggestion
evidence; LMS is the authority for resource visibility and learning-material
changes.

## Decision

Capture published course/chapter/content mutations with PostgreSQL triggers in
the originating transaction. Store a compact event journal in LMS, without
lesson bodies or per-recipient copies. Resolve current organization visibility,
enrollment and resource publication when reading. Store read receipts separately
by authenticated user and event identity.

Use a bounded outbox relay and Redis pub/sub for transient invalidation, then SSE
through the authenticated frontend BFF. Redis messages contain only `refresh`.
The durable PostgreSQL feed recovers missed hints on connect/open/visibility.
Redis failure rolls the relay transaction back, leaving events retryable;
publish-before-commit can duplicate a hint, which is harmless. Concurrent LMS
replicas claim disjoint outbox rows with `SKIP LOCKED`.

Reuse `personalize.notification.trigger` for suggestion refresh hints in a
separate LMS consumer group. Auth's existing email consumer and SMTP preferences
remain unchanged. No new broker, AI request, recipient fan-out or catalog scan
is required for in-app notifications.

## Consequences

- Source events cannot be lost between a successful course write and publication
  to an external broker. Database triggers cover existing API and internal writers.
- Trigger installation and table creation require the existing LMS DDL capability.
  V021 is installed atomically before startup, or can be applied manually first.
  A partial installation stops startup for operator recovery.
- Notification delivery is eventually consistent: the two-second relay tick,
  network and browser debounce add latency. Functional tests do not establish a
  production latency SLA.
- The feed has a 30-day serving window and bounded hourly cleanup. Burst content
  additions are grouped by chapter; publication and update budgets prevent a
  catalog release from hiding enrolled-course changes.
- Redis outages preserve the durable feed, but automatic live refresh waits for
  reconnection. Scope is revalidated on each feed read and stream reconnect;
  stale subscriptions carry no resource or personal details.
- Only known recent publication dates can be backfilled. Historical edits without
  source events cannot be reconstructed reliably.

See [the serving contract and rollout checks](../DATA_PLATFORM.md#learning-notification-feed-2026-11).
