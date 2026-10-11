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

## Implemented execution paths

Owner: Lab service / DevOps. Source of truth: `lab-service/internal/runtime/`,
`lab-service/internal/service/submission_service.go`, and `k3s/base/lab-*.yaml`.

```text
browser -> lab-service -> batched restricted Kubernetes Job (coding)
                       -> reusable learner Pod + exec stream (terminal)
                       -> dedicated PostgreSQL + restricted login (SQL)
```

These paths are synchronous HTTP/WebSocket execution. They do not depend on a
Kafka job worker. The proposed queue/worker architecture remains future work.

Coding runs all tests with the same memory cap in one Job, compiling once per
batch. Different caps use separate Jobs to preserve cgroup limits. Each test
starts a fresh process inside the submission's container; the container and
filesystem are shared within that submission. Learners never share a container.
Expected answers stay in the API. Results use base64 framing, 8 KiB diagnostics
per test, and a bounded log fetch; source is limited to 32 KiB, input to 16 KiB
per test, and grading to 50 tests. Payloads above the Linux exec argument limit
are rejected. Output files have a process file-size limit. CPU and memory are
cgroup limited; process-count isolation still depends on the node's configured
Kubelet `podPidsLimit` and must be verified before a public cohort.

The coding request has a nine-minute overall deadline; the frontend proxy allows
ten minutes to match the API write timeout. The Job deadline includes
provisioning, compilation, all tests, and kill grace;
user runtime excludes scheduling/compilation and uses `/proc/uptime` (about
10 ms precision). `timeout` enforces fractional-second limits. OOM termination
becomes `MEMORY_LIMIT`; remaining cases are pending/unexecuted. Compiler verdicts
use `COMPILE_ERROR`, matching forward migration V006. Results and the final
submission verdict commit atomically with serialized, idempotent completion.
Practice attempt reservation is serialized per learner/lab; infrastructure
failures do not consume the submission quota.

`LAB_CODING_SANDBOX_MAX_CONCURRENT_JOBS` defaults to four active submissions per
API process; SQL admits eight. Admission waits at most 30 seconds, honours
cancellation, and returns an availability error when full. Kubernetes quotas
remain the cluster-wide bound. Failed provisioning/log retrieval returns HTTP
503, rather than assigning a student's solution `RUNTIME_ERROR`. Jobs are
explicitly deleted on completion/error/cancellation; TTL is crash recovery.

Workspace sessions use one deterministic Pod per authenticated learner/lab.
`fsGroup` and `workingDir` provide a writable `/workspace`. Reconnection reuses
files until the original Pod deadline, not a renewed deadline. Closing a browser
socket closes its shell stream but does not delete the Pod. A minute janitor
removes expired/terminated Pods after an API restart too. Terminal command
verification observes context cancellation. WebSocket pings detect stale browser
connections. Reconnection starts a new shell; running shell commands and shell
variables are not persisted. Workspace files are disposable at session expiry.

The restricted `lab-sandbox` namespace, default-deny networking, quota and
allow-listed controller templates remain mandatory. Runner Pods are non-root,
read-only at the root filesystem, have writable bounded volumes, dropped
capabilities and no service-account token. The controller can access terminal
`pods/exec` within this namespace; it cannot read Secrets. A separate hardened
RuntimeClass and pinned image digests remain rollout gates, not claims of the
current generic container runtime.

## SQL practice deployment and contract

PostgreSQL is the supported secure SQL engine. MySQL/SQLServer/Oracle are
explicitly unavailable until equivalent isolated adapters exist. The API passes
`code` to `Query` and instructor `runtime_config.schema_sql` / `seed_sql` to the
runner. Each test's `input` is additional trusted fixture SQL, applied after the
shared schema/seed. Fixtures reset for each test; scripts are parsed whole by
PostgreSQL, preserving semicolons in literals and dollar-quoted statements.

`DB_LAB_POSTGRES_URL` **must target a dedicated practice instance**. It has no
fallback to the application database. The K3s service reads this from the
`lab-sql-sandbox` Secret's `postgres-url`; the practice Deployment uses its
`admin-password`. Provision these values out of band with the approved secret
management flow. The URL must match `sql_practice_admin`, `sql_practice`, and
`lab-sql-sandbox:5432` when using the included manifest; URL-encode the password.
Missing configuration fails closed with HTTP 503.

After provisioning the Secret, apply [the dedicated SQL instance](../k3s/base/lab-sql-sandbox.yaml)
explicitly, along with [sandbox policy](../k3s/base/lab-sandbox-policy.yaml)
and the updated Lab service deployment. These standalone manifests are not
implicitly enabled by base Kustomize. SQL ingress permits only Lab service Pods;
SQL egress is denied. The instance has CPU/memory/temp-file limits and stores
only disposable data on `emptyDir`. Do not put application data in it.

The admin connection initializes fixtures; submitted SQL runs over a different
connection with a random five-minute login, no administrative privileges, only
USAGE/SELECT on that submission's schema and read-only transactions. Both client
and PostgreSQL deadlines apply (default 2 seconds, maximum 10 seconds per test,
2 minutes per request). Results are bounded to 1,000 rows / 64 KiB. PostgreSQL bounds serialized
row size before sending it to the API; arrays/objects use JSON within CSV,
and timestamps use PostgreSQL JSON text formatting. Setup errors
are availability/authoring failures; query failures retain their actual verdict.
Normal cleanup drops fixtures/roles; a janitor reaps expired roles after crashes.

Expected results are CSV with a column header. Rows compare as multisets,
including duplicates, by default; `runtime_config.order_sensitive=true` enables
ordered comparison. Whitespace inside values, quoted newlines, and semicolons
are preserved. SQL NULL is rendered as `NULL` by the existing CSV convention.
Instructor schema/seed is visible to learners; hidden test-specific fixture data
and derived output are excluded from learner responses.

Compose provisions `postgres-sql-sandbox` independently from `postgres-lab`.
Its default credentials are development-only; custom passwords containing URL
special characters require an explicit URL-encoded `DB_LAB_POSTGRES_URL`.

## Validation and rollout

Run `go test ./...` in `lab-service`. Integration tests require
`BDC_LAB_SQL_TEST_URL` pointing at a disposable PostgreSQL instance and must never
use an application/production database. They verify SELECT grading, quoted
fixtures, timeouts, result caps, write denial, cross-schema denial, privilege
escalation denial, fixture reset, role cleanup, V006 and atomic/idempotent grading.
HTTP fixture tests cover batch creation, cleanup, terminal reuse, ownership, OOM,
framing, compiler timeout and output caps. Trusted shell fixtures run locally;
hostile workloads belong only on a dedicated sandbox node.

Validate Compose and Kustomize, then check frontend TypeScript/lint/build. Apply
V006 before the new runner handles compilation verdicts (API startup runs
forward migrations). Keep V006 on rollback; it is compatible with previous
per-test statuses. Rollback the runner/UI together, retaining the dedicated SQL
boundary. Disabling the SQL URL or execution flags fails closed.

Changes in source are not proof of deployment or measured latency. Before
opening a cohort, verify non-root image startup and tools for every language,
node PID caps, namespace quotas, sandbox networking, cancellation, idle expiry,
and observed scheduling/runtime separately. Pre-pull allow-listed images on
sandbox nodes to avoid first-run download latency. A future warm executor pool
requires a clean sandbox per submission and documented reset/isolation tests.

Primary references: [Kubernetes security context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/),
[Job deadlines](https://kubernetes.io/docs/concepts/workloads/controllers/job/),
and [PostgreSQL client defaults](https://www.postgresql.org/docs/18/runtime-config-client.html).

## Delivery gates

1. Build an executor image per supported language, pinned by digest; verify tools under the configured UID.
2. Create Kubernetes Jobs from an allow-listed template only; never pass a
   learner-authored command line to the controller; source/input use encoded files in the sandbox.
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
