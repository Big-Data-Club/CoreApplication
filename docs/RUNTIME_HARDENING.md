# Coding, terminal and HPC runtime hardening

## Current safety boundary

The API service is a control plane, not an execution environment.  In
production it fails closed:

- Coding `run` and `submit` do not start local processes in `lab-service`.
- Workspace/HPC terminal endpoints do not start a host shell in `lab-service`.
- HPC mock results must not be represented as completed cluster work.

`LAB_ALLOW_UNSAFE_LOCAL_EXECUTION=true` and
`LAB_ALLOW_UNSAFE_TERMINAL=true` are developer-only escape hatches.  The
application ignores both when `APP_ENV=production`.

## Required production architecture

```text
browser -> lab-service API -> job queue -> isolated executor worker -> result store
                                      -> Kubernetes Job or Slurm
```

Each executor workload must run as a non-root user with a read-only root
filesystem, dropped Linux capabilities, no service-account token, strict CPU,
memory, process-count and execution-time limits, and a default-deny network
policy.  The API service must have no permission to execute learner code.

## Delivery gates

1. Build an executor image per supported language, pinned by digest.
2. Create Kubernetes Jobs from an allow-listed template only; never pass a
   learner command line to a shell.
3. Apply namespace ResourceQuota, LimitRange, NetworkPolicy and restricted
   Pod Security admission before enabling jobs.
4. Store output with byte limits and redact internal paths.
5. Implement cancellation, TTL cleanup and an audit event per job/session.
6. Enable a small pilot cohort only after the acceptance tests below pass.

## Acceptance tests

| Area | Required proof |
|---|---|
| Coding correctness | accepted, wrong answer, compile error, runtime error, timeout |
| Resource limits | CPU loop, memory allocation, process fork attempt, output flood |
| Isolation | no host filesystem, metadata service or cross-user data access |
| Terminal | separate filesystem/session per learner; reconnect; forced expiry |
| HPC | QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED and stdout/stderr retrieval |
| Reliability | worker retry is idempotent; cancelled job cannot later become accepted |

Do not run these hostile tests against the API pod or a shared production node.
