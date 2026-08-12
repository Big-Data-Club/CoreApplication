# BDC Hub — Production DevOps Runbook

| Field | Value |
|---|---|
| Status | Active operational runbook |
| Scope | Production K3s, GitHub Actions, Docker Hub, monitoring, performance tests |
| Audience | DevOps, platform, on-call engineers, technical leads |
| Last reviewed | 2026-07-29 |

> This document intentionally contains no password, token, private IP address,
> database connection string, or Kubernetes Secret value. Retrieve sensitive
> values only from the approved password manager, GitHub Environment secrets,
> or Kubernetes Secret objects under the principle of least privilege.

## 1. Purpose and operating principles

BDC Hub runs a production LMS and AI platform on a single-node K3s cluster.
PostgreSQL, Qdrant, Neo4j, and object storage are managed external services;
Kafka and Redis run in the cluster. This runbook defines how to:

- reach the production host safely;
- assess cluster health before and after a change;
- understand the CI/CD path that is actually active today;
- release, verify, diagnose, roll back, and recover workloads;
- run load tests without contaminating production data; and
- track the platform tasks that must be completed before increasing load.

### Non-negotiable rules

1. Do not put credentials in source code, shell history, GitHub workflow logs,
   screenshots, or support tickets.
2. Do not run `kubectl delete --all`, `kubectl delete namespace`, `k3s-uninstall`,
   broad Docker prune commands, or destructive database operations during an
   incident without an approved change record.
3. Do not run stress, spike, or soak tests before the smoke test is green and
   the on-call/operations team is aware.
4. Use immutable commit-SHA image tags for production. `latest` is not a
   rollback target.
5. Treat `kubectl rollout undo` as a recovery action, not as a substitute for
   diagnosing the failed revision.

## 2. Production topology

```text
Developer push
     |
     v
GitHub Actions build (GitHub-hosted) -- pushes immutable images --> Docker Hub
     |                                                               |
     v                                                               v
Self-hosted production runner ----------------------------------> K3s node
                                                                    |
                                                                    +-- Traefik ingress
                                                                    +-- frontend / Auth / LMS / Lab / Chat
                                                                    +-- AI service + AI worker
                                                                    +-- Personalize + Recommender
                                                                    +-- Kafka + Redis
                                                                    +-- kube-prometheus-stack + Grafana
                                                                    |
                                                                    +-- External Neon / Qdrant / Neo4j / R2
```

Key Kubernetes namespaces:

| Namespace | Contents | Owner expectation |
|---|---|---|
| `default` | BDC application workloads, Kafka, Redis, ingress objects, test Jobs | App + DevOps |
| `monitoring` | kube-prometheus-stack, Grafana, Alertmanager, node exporter | DevOps |
| `kube-system` | K3s system workloads, Traefik, CoreDNS, metrics-server | Platform only |

The current cluster is intentionally single-node. A node, disk, CNI, or
Kubernetes control-plane failure is therefore a production outage; there is no
node-level failover.

## 3. Secure access: VPN then SSH

### 3.1 Prerequisites

- Be approved for the production VPN group.
- Use an individual account; never share an SSH account or password.
- Store credentials and recovery codes only in the approved password manager.
- Prefer an SSH key or managed short-lived credential when the access process
  supports it.

### 3.2 Connection procedure

1. Connect to the corporate VPN and confirm that the private production network
   is reachable.
2. Use the managed SSH alias if it has already been provisioned:

   ```bash
   ssh bdc
   ```

   Otherwise use the user and private host supplied by the access inventory:

   ```bash
   ssh <approved-ops-user>@<production-private-host>
   ```

3. Confirm the target before doing any work:

   ```bash
   hostname
   id
   date -Is
   kubectl get nodes
   ```

4. Work from the non-root operations account. Use `sudo` only for a documented
   host-level operation. K3s administration should normally use `kubectl`.

### 3.3 SSH safety

- Never pass a password in a command-line argument, script, environment file,
  or copied terminal transcript.
- Do not alter `/etc/ssh/sshd_config`, firewall policy, K3s kubeconfig
  permissions, or VPN configuration during an application incident unless the
  change has been approved.
- Do not copy `/etc/rancher/k3s/k3s.yaml` off the production host. It grants
  cluster-admin access.
- End the VPN session when finished.

## 4. First five minutes: standard cluster health check

Run the following read-only commands after connecting and before a release,
load test, or incident action.

```bash
kubectl get nodes -o wide
kubectl get pods -A -o wide
kubectl get deploy,statefulset,daemonset -A
kubectl get events -A --sort-by=.lastTimestamp | tail -n 80
kubectl top nodes
kubectl top pods -A --sort-by=cpu
```

Expected baseline:

- the only node is `Ready`;
- all application and monitoring pods are `Running` and ready;
- no unexpected `CrashLoopBackOff`, `ImagePullBackOff`, `Pending`, or
  `Terminating` pod remains for more than a few minutes;
- Prometheus and Grafana pods in `monitoring` are ready; and
- node CPU, memory, and ephemeral disk have headroom before a release or test.

### Focused checks

```bash
# Application state
kubectl -n default get pods -o wide
kubectl -n default get deploy
kubectl -n default get svc,ingress

# Monitoring state
kubectl -n monitoring get pods
kubectl -n monitoring get prometheus,servicemonitor,podmonitor

# K3s and Traefik
kubectl -n kube-system get pods
kubectl -n kube-system logs deploy/traefik --tail=200

# Recent warning/error events only
kubectl get events -A --sort-by=.lastTimestamp \
  | grep -E 'Warning|Failed|BackOff|Unhealthy|Evicted' || true
```

### Workload inspection commands

```bash
# Replace SERVICE or POD with an exact name.
kubectl -n default describe deployment/<SERVICE>
kubectl -n default get rs -l app=<SERVICE>
kubectl -n default get pods -l app=<SERVICE> -o wide
kubectl -n default describe pod/<POD>
kubectl -n default logs <POD> --all-containers --tail=300
kubectl -n default logs <POD> --all-containers --previous --tail=300

# Read the currently deployed image and rollout history.
kubectl -n default get deployment/<SERVICE> \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}{"="}{.image}{"\n"}{end}'
kubectl -n default rollout history deployment/<SERVICE>
```

## 5. Current CI/CD design — source of truth

The repository has more than one workflow. The following table prevents a
common operational mistake: assuming every workflow deploys every service.

| Workflow | Trigger | Current role | Important limitation |
|---|---|---|---|
| `.github/workflows/production.yml` | Push to `main`, or manual dispatch | **Primary production build and deployment path** | Its change matrix currently covers only AI, Recommender, Personalize, and LMS. |
| `.github/workflows/ci.yml` | PR to `main`/`dev`/release, push to `dev`/release, manual | Quality CI: detect, test, build, and conditionally publish images | It does **not** run on a push to `main`. |
| `.github/workflows/cd-production.yml` | Completion of `CI - Build, Test & Push`, or manual | Legacy/selective restart workflow | It may restart deployments but is not the normal SHA-based main production path. Review before use. |
| `.github/workflows/frontend-pointer-deploy.yml` | Frontend submodule pointer update on `main` | Frontend-specific deployment path | Frontend is managed separately from the primary service matrix. |

### 5.1 Primary production pipeline

The normal `main` release path is `production.yml`:

1. **Detect changes**
   - `dorny/paths-filter` determines whether `ai-service`,
     `recommender-service`, `personalize-service`, or `lms-service` changed.
   - AI changes select both `ai-service` and `ai-worker` because they share the
     same image.
2. **Build**
   - GitHub-hosted runners build `linux/amd64` images with Buildx.
   - Images are pushed to Docker Hub as both the immutable commit SHA and
     `latest`.
3. **Deploy**
   - The self-hosted runner configured with
     `self-hosted, linux, x64, production` runs on the production environment.
   - It refreshes the `dockerhub-registry` pull secret and patches the default
     service account to use it.
   - It calls `scripts/deploy-production.sh` with `IMAGE_TAG=<Git SHA>` and an
     explicit comma-separated `SERVICES` list.
4. **Verification and rollback**
   - The script waits for each selected deployment to roll out.
   - If any wait fails, its trap resets every deployment changed by that run to
     the image recorded immediately before the update.

### 5.2 No-change, skipped, success, and deployed: exact meanings

"Green" does not always mean that an image was built or that production was
changed. Read the outputs of **Select production workloads** before treating a
workflow run as a release.

#### `production.yml` — the normal `main` production path

On every push to `main`, the `detect-changes` job always runs. It only selects
these paths and workloads:

| Changed path category | Selected image build | Selected deployment rollout |
|---|---|---|
| `ai-service/**`, AI manifest, shared ConfigMap, or deploy script | `bdc-ai` | `ai-service`, `ai-worker` |
| `recommender-service/**`, recommender manifest, shared ConfigMap, or deploy script | `bdc-recommender` | `recommender-service` |
| `personalize-service/**`, personalize manifest, shared ConfigMap, or deploy script | `bdc-personalize` | `personalize-service` |
| `lms-service/**`, LMS manifest, or deploy script | `bdc-lms` | `lms-service` |
| Anything outside the rows above | none | none |

If a commit changes only documentation, performance-test assets, Chat, Lab,
Auth, frontend, or another unlisted path, the detector writes:

```text
should_build=false
matrix={"include":[]}
services=
```

The **Build** job and **Roll out production** job then display **Skipped** in
GitHub Actions. The overall workflow can still finish **Success** because this
is an intentional no-op. In that case there is no Docker build, no Docker Hub
push, no self-hosted runner use, no ConfigMap apply, no `kubectl set image`, and
no restart. This is the expected status, not a CI/CD failure.

If one or more selected paths change, only the matching images are built and
pushed with the immutable commit SHA (and currently `latest`), and only the
matching deployments are changed to the SHA. A multi-service commit produces a
small matrix and deploys the combined explicit service list; unrelated
workloads remain untouched.

For **Run workflow** with both `image_tag` and `services`, a skipped Build job
is also expected: the workflow deliberately does not rebuild and rolls out the
already-published immutable tag to exactly the requested deployments. The
Deploy job must run. If `image_tag` is provided without `services`, detection
fails deliberately and production is not changed. Do not use `latest` as the
manual tag.

For a manual run without `image_tag`, the deploy input resolves to the current
commit SHA, but deployment still depends on the change detector selecting
services. Therefore it is not a safe "redeploy everything" control. Use a
manual run with an existing immutable `image_tag` and an explicit `services`
list when an intentional redeploy or rollback is needed.

#### `ci.yml` — quality CI, not the normal main release

This workflow runs for pull requests to `main`, `dev`, and `release/*`; pushes
to `dev` and `release/*`; and manual dispatch. It does **not** run for a push
to `main`, so it does not gate or trigger the primary `main` production path.

Its `any_change` flag is true only for Auth/backend, frontend, LMS, AI, Chat,
Lab, Personalize, Recommender, or `force_build_all=true`. A change only under
`k3s/**`, `docker-compose*.yml`, or `.github/workflows/**` is detected in the
separate `docker` output but is not included in `any_change`; it currently
causes no application build or test.

When `any_change=false`, `build-and-test` and `security-scan` are **Skipped**;
`ci-summary` runs and records **No Changes — Skipped build**. No image is
built or pushed. When `any_change=true`, the eight-entry matrix is created.
Only changed services run checkout, tests, application build, and optional
image push. Matrix entries for unchanged services run the initial "Skip if no
changes" step and normally finish **Success** with their remaining steps
skipped. Thus the matrix job can be green even though only one service was
actually built; use the detector outputs and individual step logs to identify
which one.

An important current defect: this workflow triggers on `dev`, but its image
push condition allows `main`, `develop`, and `release/*` (not `dev`). As a
result, a normal push to `dev` can test and build an application but must show
`should_push=false` and will not publish an image. Treat that as current
configuration behavior, not as a registry outage; fix the branch-name mismatch
before relying on `dev` images.

#### `cd-production.yml` — legacy restart path

This workflow does not set an image tag or build an image. It calls `kubectl
rollout restart` for one deployment or all known deployments, then asks
Kubernetes to wait up to 180 seconds per target. It also prunes unused Docker
images/containerd images in its final cleanup step. A successful run never
means a new commit reached production: it is only a restart of the image
already configured in Kubernetes.

More importantly, the restart and rollout-status commands are followed by
`|| echo`, so their failures are logged as warnings rather than failing the
job. A legacy-CD **Success** is therefore not proof that every target became
ready. Operators must run `kubectl rollout status`, inspect pods/events, and
check the application explicitly after this workflow. Do not run its manual
`all` target casually, because it can restart every known workload and trigger
the image-cache cleanup.

Its automatic trigger waits for a successful `CI - Build, Test & Push` run on
`main` or `develop`. Because `ci.yml` does not run on `main` and uses `dev`
rather than `develop` for push triggers, this automatic legacy CD path is not
the normal route for either current branch. Manual dispatch is a restart-only
operation and must be treated as production-impacting: select one target where
possible, check its current image first, and do not use it as a substitute for
the SHA-based primary deployment workflow.

| GitHub status or observation | Operational meaning | Required interpretation/action |
|---|---|---|
| **Skipped** Build and **Skipped** Deploy in `production.yml` | No selected production paths changed. | Expected no-op; no release happened. |
| **Success** workflow, but Build is skipped | Detection/manual-tag policy intentionally avoided a build. | Confirm whether Deploy ran and inspect `services` output. |
| **Success** Deploy in `production.yml` | Selected deployments passed rollout status after a SHA update. | Still run service smoke checks and inspect the deployed image. |
| **Success** in legacy CD | The restart workflow completed; errors may only have been logged as warnings. | Do not call it a new release; independently inspect image, rollout, events, and logs. |
| **Cancelled** | A newer run or an operator stopped it. | Inspect current image/pod state before retrying. |
| **Failure** | A detector, build, registry, runner, rollout, or verification step failed. | Follow section 7; do not infer whether rollback fully completed without checking the cluster. |

#### Required verification after every CI/CD run

1. In Actions, open the run summary and record the commit SHA, detector output
   (`should_build`, `services`, or `any_change`), and each selected matrix
   entry.
2. For a production run, confirm the Build job pushed the exact immutable SHA,
   then confirm **Roll out production** ran on the self-hosted runner. A green
   detector alone is not a deployment.
3. From the approved VPN/SSH session, compare Kubernetes to the intended SHA:

```bash
kubectl -n default get deployment ai-service \
  -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}'
kubectl -n default rollout status deployment/ai-service --timeout=12m
kubectl -n default get pods -l app=ai-service -o wide
```

4. Run the selected service's smoke check and record the result in the release
   ticket. A ready pod is necessary but does not prove its API dependencies are
   healthy.

### 5.3 What `scripts/deploy-production.sh` does

The deploy script is intentionally conservative:

```text
verify kubectl access
  -> apply k3s/base/configmap.yaml
  -> apply recommender manifest only when that service is selected
  -> record each selected Deployment's current image
  -> kubectl set image ...:<immutable SHA>
  -> kubectl rollout status for each selected Deployment
  -> on error: restore only images changed by this invocation
```

It does **not** apply the full Kustomize base during each release, so a stale
manifest cannot overwrite unrelated deployment images. It also does not
delete persistent volumes.

### 5.4 Manual deployment of a known immutable image

Use **Actions → Build and deploy production → Run workflow** only after the
image exists in Docker Hub.

- `image_tag`: exact immutable commit SHA.
- `services`: explicit list, for example `ai-service,ai-worker`.

Never enter `latest` as a production rollback version.

## 6. Release checklist

### Before merge or manual dispatch

- [ ] Pull request reviewed; CI checks are green.
- [ ] Required Docker Hub repositories and GitHub `production` Environment
      secrets are present.
- [ ] Change scope matches the service matrix. If it does not, do not assume
      the main production workflow will deploy it.
- [ ] Cluster baseline in section 4 is healthy.
- [ ] The team knows whether the release may restart AI/worker workloads and
      temporarily warm models.
- [ ] A rollback SHA/revision is known.

### During deployment

```bash
# Watch selected deployments and pods.
kubectl -n default get deployment,pod -w

# In another terminal, watch events.
kubectl get events -A --watch
```

### After deployment

```bash
# Replace each name with the services actually released.
kubectl -n default rollout status deployment/ai-service --timeout=12m
kubectl -n default rollout status deployment/ai-worker --timeout=12m
kubectl -n default get pods -o wide
kubectl top pods -n default --sort-by=cpu

# Public route checks; use only endpoints known to be intentionally public.
curl -fsS -o /dev/null -w 'frontend %{http_code} %{time_total}s\n' https://<public-domain>/
curl -fsS -o /dev/null -w 'auth %{http_code} %{time_total}s\n' https://<public-domain>/apiv1/actuator/health
```

Record the deployed SHA, workflow URL, services, rollout duration, and health
result in the change record.

## 7. Playbook: `ai-service` rollout exceeds its progress deadline

### 7.1 Example symptom

```text
Waiting for deployment "ai-service" rollout to finish: 1 old replicas are pending termination...
error: deployment "ai-service" exceeded its progress deadline
Deployment failed; rolling back workloads changed by this run.
```

This means the deployment controller did not reach its desired ready state
inside its progress deadline. The line about an old replica is a symptom, not
the root cause. Do not simply rerun the workflow repeatedly.

The deploy script in this repository restores the images for services it
changed in that invocation. Confirm the state before any manual action.

### 7.2 Immediate triage — read-only first

```bash
export NS=default
export SERVICE=ai-service

kubectl -n "$NS" rollout status deployment/$SERVICE --timeout=30s || true
kubectl -n "$NS" get deployment/$SERVICE -o wide
kubectl -n "$NS" describe deployment/$SERVICE
kubectl -n "$NS" get rs -l app=$SERVICE -o wide
kubectl -n "$NS" get pods -l app=$SERVICE -o wide
kubectl -n "$NS" get events --sort-by=.lastTimestamp | tail -n 120
kubectl top nodes
kubectl top pods -n "$NS" --sort-by=memory
```

For every new and old replica involved:

```bash
kubectl -n "$NS" describe pod/<POD>
kubectl -n "$NS" logs <POD> --all-containers --tail=300
kubectl -n "$NS" logs <POD> --all-containers --previous --tail=300
```

### 7.3 Root-cause decision table

| Evidence | Likely cause | Correct next action |
|---|---|---|
| `ImagePullBackOff`, `ErrImagePull`, registry auth errors | Image tag absent, wrong image name, or stale Docker Hub pull secret | Verify the exact SHA exists in Docker Hub; check `dockerhub-registry`; do not retry until corrected. |
| `OOMKilled`, memory near limit, node memory pressure | Model load or Python worker exceeds pod/node memory | Inspect model cache and resource limits; reduce concurrency or raise approved memory limit; retry only after capacity review. |
| `startupProbe`/`readinessProbe` failures | Model warm-up, dependency connectivity, bad health path, or timeout too short | Read app logs and probe events; verify Qdrant/Neo4j/DB reachability; fix app/config or adjust an approved probe budget. |
| Old pod remains `Terminating` | Long shutdown, stuck process, finalizer, volume unmount, or node/container runtime issue | Inspect pod events and process logs. Do not force-delete until the impact and volume ownership are understood. |
| New pod ready but rollout still blocked | Deployment strategy, unavailable replica, PDB, or old ReplicaSet issue | Inspect Deployment conditions, ReplicaSets, `maxSurge`, `maxUnavailable`, and PDBs. |
| DNS/TLS/connection errors to external services | VPN/DNS/egress/external provider problem | Validate from the pod and compare with provider status; do not roll forward blindly. |

### 7.4 Safe recovery

1. Confirm whether the script already restored the prior image:

   ```bash
   kubectl -n default get deployment/ai-service \
     -o jsonpath='{.spec.template.spec.containers[?(@.name=="ai-service")].image}{"\n"}'
   kubectl -n default get deployment/ai-worker \
     -o jsonpath='{.spec.template.spec.containers[?(@.name=="ai-worker")].image}{"\n"}'
   kubectl -n default rollout history deployment/ai-service
   ```

2. If rollback did not complete, use the exact previous revision only after
   approval:

   ```bash
   kubectl -n default rollout undo deployment/ai-service --to-revision=<REVISION>
   kubectl -n default rollout undo deployment/ai-worker --to-revision=<REVISION>
   kubectl -n default rollout status deployment/ai-service --timeout=12m
   kubectl -n default rollout status deployment/ai-worker --timeout=12m
   ```

3. Record the failed SHA, events, pod logs, resource readings, and final
   deployed SHA. Create a follow-up issue with the evidence.

### 7.5 Preventing a recurrence

- Pre-warm or pre-bake the AI model cache where feasible.
- Set realistic startup/readiness probes based on measured cold-start time.
- Add a pre-deployment resource check for memory headroom and pending pods.
- Make the deploy script wait for a completed rollback, not only issue
  `kubectl set image` during the error trap.
- Add a canary or one-service deployment path for AI before rolling AI worker
  and unrelated services.

## 8. Monitoring and performance-testing operations

### 8.1 Monitoring stack

The active stack is `kube-prometheus-stack` in namespace `monitoring`.
Grafana is served through the existing protected monitoring route. Prometheus
remote-write is enabled for k6 but must remain cluster-internal; never expose
`/api/v1/write` through a public Ingress.

```bash
kubectl -n monitoring get pods
kubectl -n monitoring get prometheus
kubectl -n monitoring get servicemonitor,podmonitor
kubectl -n monitoring get pvc
```

The versioned dashboard and ServiceMonitor manifests are under
`k3s/observability/`. Validate before applying:

```bash
kubectl kustomize k3s/observability/
kubectl apply --dry-run=client -k k3s/observability/
kubectl apply -k k3s/observability/
```

Apply ServiceMonitors only after the corresponding service image exposes the
configured metrics endpoint. A target that does not expose `/metrics` creates
an `UP=0` alert/noise, not useful observability.

### 8.2 Performance test safety model

All scripts live in `performance-tests/` and must use:

- dedicated test accounts;
- one dedicated published Test Course;
- an isolated Kubernetes Job or an external load generator;
- a unique `TEST_ID`; and
- the Grafana **BDC Performance** dashboard.

Never run a large test directly on the application VM because the generator
would consume the very CPU/network capacity being measured. A small 5-VU
pipeline smoke Job is an exception used only to validate telemetry.

### 8.3 Required sequence

| Phase | Permitted load | Goal | Gate to proceed |
|---|---:|---|---|
| Pipeline smoke | 5 VU, 1 minute | Verify k6 remote-write and Grafana | Metrics visible, no routing/configuration errors |
| Core smoke | 5 VU, 1 minute | Validate auth and representative user journeys | Error <1%, p95 <800 ms |
| Defensive load | 20 → 50 → 100 → 200 VU, each 5–10 minutes | Measure normal/peak behavior | Current stage remains green and no saturation warning |
| Approved ceiling | Maximum 300 VU | Establish upper bound for this test window | Stop at first sustained SLA breach or at 300 VU |
| Soak | Moderate fixed load, typically 2 hours | Detect leaks and slow degradation | Prior load stage green and ops monitoring live |

Stop immediately when error rate is at least 1%, p95 exceeds 800 ms for two
minutes, p99 exceeds 2 seconds, a pod restarts, CPU throttling is sustained,
or node memory pressure appears.

### 8.4 Current test finding

The most recent core smoke test intentionally stopped before load testing:

| Metric | Result | Interpretation |
|---|---:|---|
| Virtual users | 5 | Smoke level only |
| HTTP error rate | 25% | Fails the <1% gate |
| p95 request duration | 828.7 ms | Fails the <800 ms gate |
| Failing routes | Flashcards due; student heatmap | Must be diagnosed before raising load |
| Passing routes | Login, course list/detail/progress, chat channels | Basic routing/auth works |

The test created 85 student, 12 teacher, and 3 admin accounts plus a dedicated
Test Course. Their credentials are stored in Kubernetes Secrets and must never
be copied into this document. The test data requires an approved cleanup Job
after the investigation is complete.

### 8.5 Pre-load observability requirement

Before defensive load testing, deploy application-level metrics:

- Auth already exposes Spring Actuator Prometheus metrics.
- AI, Personalize, and Recommender source now contains Prometheus HTTP
  instrumentation but needs image build and rollout.
- LMS, Chat, and Lab need `/metrics` instrumentation before their
  ServiceMonitors are applied.
- Add database-pool, Redis, Kafka consumer lag, and dependency latency metrics
  where supported. Kubernetes CPU/RAM alone is insufficient to identify a SQL,
  cache, or Kafka bottleneck.

## 9. Current DevOps task backlog

Priorities are ordered. Do not start a 20+ VU test until P0 is complete.

### P0 — restore reliable smoke and observability

- [ ] Diagnose and fix the non-2xx result from the Test Course flashcard-due
      route.
- [ ] Diagnose and fix the non-2xx result from the student heatmap route.
- [ ] Repeat core smoke; it must meet error <1% and p95 <800 ms.
- [ ] Build and deploy AI, Personalize, and Recommender images containing the
      newly added Prometheus instrumentation.
- [ ] Instrument LMS, Chat, and Lab; build and deploy those images; then apply
      only their matching ServiceMonitors.
- [ ] Confirm the BDC Performance dashboard has k6, node, pod, and application
      endpoint metrics for the same `TEST_ID`.
- [ ] Ensure the Prometheus remote-write receiver change is persisted through
      the Helm values/release process, not only an emergency live patch.

### P1 — make CI/CD deterministic and complete

- [ ] Consolidate the three workflow paths or clearly deprecate the legacy
      path. There must be one documented production release authority.
- [ ] Resolve the `dev` versus `develop` branch mismatch in `ci.yml` and
      `cd-production.yml`; decide which branch may publish non-production
      images and make both trigger and `should_push` conditions match it.
- [ ] Decide whether changes limited to Kubernetes manifests, Compose files,
      workflow files, or deployment scripts must run validation. The current
      `docker` detector does not make `any_change=true`, so those changes can
      appear as a successful CI run with no build or test.
- [ ] Add a per-service CI summary instead of repeating one matrix-job result
      for every row; the current summary can look green even when most matrix
      entries intentionally performed no build.
- [ ] Extend `production.yml` detection/build/deploy matrix to cover Auth,
      Chat, and Lab, or document their approved independent deployment path.
- [ ] Verify frontend deployment ownership: the primary production workflow
      does not build it, while the frontend-pointer workflow does.
- [ ] Align Go toolchain versions in CI with the Go versions declared in the
      service `go.mod` files; the current quality workflow configures Go 1.21
      while services declare newer Go versions.
- [ ] Make rollback verification explicit: after restoring images, wait for
      every rolled-back Deployment to become ready and fail the workflow if it
      does not.
- [ ] Add post-deploy smoke checks per selected service, with public and
      in-cluster routes clearly separated.
- [ ] Add artifact links for pod descriptions, events, and relevant logs when a
      deployment fails.

### P2 — operational resilience

- [ ] Define alerts for pod restarts, unavailable replicas, image pull errors,
      node disk pressure, memory pressure, CPU throttling, and Kafka lag.
- [ ] Document a tested backup/restore procedure for external databases and
      Kubernetes persistent volumes.
- [ ] Create and review the cleanup Job for performance-test accounts, Test
      Course, enrollments, and generated analytics data.
- [ ] Establish a release calendar, on-call rota, and incident communication
      channel for production load tests.
- [ ] Evaluate a second K3s node or a documented disaster-recovery plan; the
      current topology has a single-node failure domain.

## 10. Incident communication template

Send this before a load test or when a deployment starts failing. Replace text
inside angle brackets; do not include credentials.

```text
[BDC Production] <planned performance test | deployment incident>
Time window: <start> to <end>, ICT
Scope: <services / release SHA / test ID>
Expected impact: <none | possible latency during AI rollout | other>
Guardrails: error <1%, p95 <800 ms, stop on pod restart or resource pressure
Monitoring: Grafana BDC Performance dashboard, Kubernetes events, on-call channel
Owner: <name>
Rollback/stop owner: <name>
```

## 11. Useful references

- [Primary production workflow](../.github/workflows/production.yml)
- [Quality CI workflow](../.github/workflows/ci.yml)
- [Deployment script](../scripts/deploy-production.sh)
- [K3s deployment guide](../k3s/DEPLOYMENT.md)
- [Performance test assets](../performance-tests/README.md)
- [Observability manifests](../k3s/observability/kustomization.yaml)
