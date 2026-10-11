# ADR-8: Batch coding tests and separate interactive/SQL execution

Status: Accepted for implementation; production rollout pending validation.
Owner: Lab service / DevOps. Date: 2026-10-11.

## Context

The coding adapter scheduled a new Job and compiled source for every test;
Job deadlines excluded image-pull/scheduling time. Terminal Pods lacked writable
workspace ownership and were deleted when a browser disconnected. SQL requests
did not forward code/schema/seed to the adapter, used pooled connections after
changing schema, and production reused the application database credentials.
Compilation verdicts also disagreed with database constraints, while persistence
errors were ignored.

## Decision

Use one restricted Kubernetes Job per submission/memory-limit batch, compiling
once with fresh test processes. Never share containers across learners. Keep
expected answers in the API, frame bounded output, separate orchestration errors
from learner verdicts, and include provisioning in lifecycle deadlines.

Keep a non-root terminal Pod per learner/lab until its original expiry. Reconnect
shell streams without deleting files; remove expired Pods with a janitor.

Run SQL on a separate PostgreSQL instance, using a fresh restricted login and
schema per request, reset fixtures per case, read-only transactions and deadlines.
Default to multiset CSV comparison with optional ordered results. Other engines
fail closed pending equivalent isolation. Commit grading results atomically and
idempotently with the canonical `COMPILE_ERROR` status and forward migration V006.

## Consequences

Typical grading eliminates N-1 pod starts/compilations for N equal-cap tests.
Scheduling latency still exists once per submission; this is not a measured
production speedup. Mixed caps require separate batches. Tests within a coding
submission share a filesystem; this is not per-case filesystem isolation.
Node PID limits and hardened RuntimeClass/image validation remain rollout gates.

SQL avoids pod startup for queries but requires a dedicated instance/Secret and
operator-managed credentials. Login expiry and janitors recover leaked fixtures
after crashes. Terminal files last only until Pod expiry; reconnection does not
restore shell processes or variables. Browser drafts are local, scoped to learner,
lab and language, and may be unavailable when browser storage is disabled.

A warm execution pool and asynchronous queue can follow after clean per-request
sandbox/reset semantics and lifecycle tests exist. No Kafka execution contract
is added by this change. See [runtime operations](../RUNTIME_HARDENING.md).
