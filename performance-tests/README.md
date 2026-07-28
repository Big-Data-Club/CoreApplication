# BDC performance tests

`k6_core_journeys.js` is a production-safe, read-only workload: each virtual
user logs in and makes representative `GET` requests only. It must use
dedicated test accounts, an existing test course, and a scheduled test window.
No credential or secret is stored in this directory.

## Profiles

| `TEST_TYPE` | Purpose | Default load |
|---|---|---|
| `smoke` | Validate credentials, routes, and telemetry | 5 VUs / 1 minute |
| `load` | Expected peak | 25 VUs / 5 minutes |
| `stress` | Find the saturation point | 50 → 100 → 200 VUs |
| `spike` | Sudden traffic burst | 150 VUs |
| `soak` | Detect leaks and connection exhaustion | 25 VUs / 2 hours |

Stress, spike, and soak must be approved for the target environment. Start
with smoke, then load; stop immediately if the Grafana guardrails trigger.

## Required runtime variables

```bash
export BASE_URL=https://bdc.hpcc.vn
export COURSE_ID=123
export TEST_ID=perf-20260728-load-01
export TEST_TYPE=smoke
export STUDENT_ACCOUNTS='[{"email":"perf.student.001@example.invalid","password":"..."}]'
export TEACHER_ACCOUNTS='[{"email":"perf.teacher.001@example.invalid","password":"..."}]'
export ADMIN_ACCOUNTS='[{"email":"perf.admin.001@example.invalid","password":"..."}]'
```

Use at least as many accounts as the peak VUs for each role wherever possible;
otherwise sessions and rate limits may be unrealistically shared. The role mix
is 85% student, 12% teacher, and 3% admin.

## Run from a separate load generator

Do not run a large test on the application VM: it would consume the CPU and
network capacity that is being measured. From an external generator that can
reach the cluster Prometheus service:

```bash
K6_PROMETHEUS_RW_SERVER_URL=http://kps-kube-prometheus-stack-prometheus.monitoring.svc:9090/api/v1/write \
K6_PROMETHEUS_RW_TREND_AS_NATIVE_HISTOGRAM=true \
k6 run --out experimental-prometheus-rw performance-tests/k6_core_journeys.js
```

Prometheus must have `enableRemoteWriteReceiver: true`; this is recorded in
`k3s/kube-prometheus-stack/values.yaml`. Open the **BDC Performance** dashboard
in Grafana and choose `TEST_ID` before the run begins.

For a generator outside the cluster, expose this endpoint only through a
temporary authenticated tunnel. Never expose Prometheus remote write publicly.

## Success criteria and stop conditions

The script fails when HTTP errors reach 1%, p95 exceeds 800 ms, or p99 exceeds
2 seconds. Stop a production run early when any of these conditions persists
for two minutes, a pod restarts, CPU throttling exceeds 5%, or node memory
pressure begins. Record the last completed VU stage as the safe concurrency;
the previous stage is the recommended capacity with headroom.
