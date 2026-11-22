# BDC Hub - Production DevOps Runbook

| Field | Value |
|---|---|
| Status | Active operational runbook |
| Scope | Production K3s, GitHub Actions, Docker Hub, monitoring, performance tests |
| Audience | DevOps, platform, on-call engineers, technical leads |
| Last reviewed | 2026-08-29 |

> This document intentionally contains no password, token, private IP address,
> database connection string, or Kubernetes Secret value. Retrieve sensitive
> values only from the approved password manager, GitHub Environment secrets,
> or Kubernetes Secret objects under the principle of least privilege.

## 1. Purpose and operating principles

LMS safety rollout (2026-11): apply
[`AI V025`](../../ai-service/migrations/releases/2026-11/V025__review_delivery_receipts.sql) and
[`LMS V022`](../../lms-service/migrations/releases/2026-11/V022__lms_request_safety.sql) to their
respective owner databases before releasing the images. New LMS fails startup
when its required safety tables are absent. Deploy the AI receiver first, then
LMS: review delivery retries require the new receiver's idempotency receipts.
Both migrations are additive; retain their tables on rollback. Do not roll AI
back behind the compatible receiver while new LMS workers are still delivering.
A rollback to old LMS reopens corrected authorization paths; use a forward fix
or an explicitly reviewed front-door restriction rather than a blind rollback.

Apply the matching ingress/deployment manifest: `/ready` replaces `/health` for
readiness only, media responses must not receive public immutable cache headers,
and the LMS/media ingress uses the coarse edge rate limiter. Purge existing
public CDN/proxy cache entries for protected media as part of rollout; changing
origin headers cannot revoke copies already cached with the old one-year TTL.
Verify that the object bucket has no anonymous read policy or public custom
endpoint; API ACLs cannot protect a directly public bucket. No bucket policy or
live CDN setting is changed by this source patch.

For the browser file-session fix, release the matching frontend image and
`bdc-ingress-files` route together: `/files` targets frontend port 3001 without
`default-rewrite-files`. Next.js rewrites it to the session-aware `/api/files`
BFF, which sends the user's Bearer token to LMS. Routing directly to LMS loses
the NextAuth identity and can return `file_not_found` for existing private files.
Verify a protected PDF from a fresh signed-in browser session, including a byte
range request; an anonymous request must still fail. Cached success on another
browser does not verify the deployed authentication path.

New document/video uploads are private by default; legacy unregistered non-image
objects require audited reconciliation to an owner/course before access. Inventory
those objects and course thumbnails before rollout; do not guess an owner from a
UUID or silently make them public. Preserve explicitly public passive images used
by current import/thumbnail callers. Confirm `AI_SERVICE_SECRET` is a configured
strong secret shared by the internal callers; placeholder service secrets are
rejected. Verify that local LMS role synchronization has caught up before rollout;
a valid JWT no longer substitutes for missing/revoked local role assignments. Cookie-authenticated writes now reject untrusted browser origins; keep
`CORS_ALLOWED_ORIGINS` aligned with approved frontend origins.

Configure `LMS_TRUSTED_PROXY_CIDRS` for the actual ingress/BFF proxies and verify the resolved client IP before enabling traffic; unconfigured proxy clients share one coarse IP budget. Do not trust every RFC1918 address.

Start with the documented request budgets in the developer guide. Monitor 429/503,
DB connection waits/lock latency, pending quiz effects (including local vs remote
completion), retry age, Kafka lag/DLQ and temp-disk/storage usage. Redis outages
retain local rate limits; AI outages retain local learning progress. Do not raise
replicas or pool sizes without a total database connection budget. These changes
are not a load-test result; follow the existing approved performance procedure on
staging before claiming capacity. Application limits cannot absorb volumetric
DDoS once upstream bandwidth is exhausted.

Workspace is selected by the existing production workflow for changes to its
service or manifests. Provision its configuration before pushing the release;
missing Workspace DB/origin configuration stops the rollout. See [the service guide](../../workspace-service/README.md)
for its dedicated PostgreSQL database, direct LISTEN connection, backup scope,
WebSocket edge route, allowed origins, frontend runtime address and limits.
`k3s/workspace` uses one replica without surge, and applies migrations before
readiness. Migration 009 retains only four snapshots/page; 010 enables notebook
copies into authorized team spaces. AI Workspace is disabled by default.
A frontend pointer change alone does not provision Workspace infrastructure.

Studio/MCP rollout (2026-10-21): apply AI migration V022 before deploying the
matching HTTP, worker and frontend images. New Studio artifacts require a
separate private unversioned MinIO bucket (default `<MINIO_BUCKET>-studio-temporary`),
without a bucket access policy. Worker credentials need create/put/get/delete/list
and bucket policy/versioning inspection permission. Never apply a whole-bucket
TTL: `source/` persists, while `temporary/` video/audio/ZIP expire ten minutes
after ready. Cleanup is an independent 15-second worker loop with retries;
access expires even if deletion is temporarily unavailable. Track cleanup attempts
and oldest unpurged expiry in `studio_temporary_media`; do not delete manifests
before their objects are removed.

YouTube uploads target the shared admin channel. Set the existing OAuth variables,
enable uploads and reconnect once via `/lms/admin/youtube-manage`: old local token
files are not imported. The encrypted AI-owned connection replaces frontend
ephemeral storage and requires the stable `AI_KEY_ENCRYPTION_SECRET`. The AI worker
calls the secret-authenticated `STUDIO_YOUTUBE_BRIDGE_URL` (K3s default
`http://frontend:3001/api/internal/studio-youtube`); no public browser proxy may
expose this bridge or `/ai/studio/youtube/connection`. Keep signed download query
tokens out of HTTP logs. Drain old workers before rollout/rollback: pre-V022
workers write nonexpiring public video objects. Legacy video/audio/ZIP objects are
retired automatically; preserve projects for re-render. See the
[authoring operations contract](../CONTENT_AUTHORING_PIPELINE.md#private-artifacts-video-retention-and-shared-youtube).

BDC Hub runs a production LMS and AI platform on a single-node K3s cluster.
PostgreSQL, Qdrant, Neo4j, and object storage are managed external services;
Kafka and Redis run in the cluster. This runbook defines how to:

- reach the production host safely;
- assess cluster health before and after a change;
- understand the CI/CD path that is actually active today;
- release, verify, diagnose, roll back, and recover workloads;
- run load tests without contaminating production data; and
- track the platform tasks that must be completed before increasing load.

### Related recovery trajectories

- [PostgreSQL migration through Grafana /monitor](../operations/POSTGRES_ONLINE_MIGRATION.md):
  push-main deployment of the migration console/dashboard, logical replication,
  shared deployment lock, runtime Secret cutover and recovery. First use requires
  the documented Grafana dashboard setup and profile enablement.
  Each run accepts source and destination URLs in `/monitor/migrations/`; success
  promotes that destination to the next source. Later pushes preserve Secrets
  and the enabled profile. The migration image defaults to PostgreSQL 18;
  `MIGRATION_PG_MAJOR` must match both endpoints. Read the migration state
  ConfigMap for preflight errors before retrying.

- [Neon PostgreSQL cutover and K3s recovery - 2026-08-29](../operations/NEON_CUTOVER_2026-08-29.md):
  six-database migration, runtime Secret recovery, disk-pressure remediation,
  Redis credential synchronization, and Neon pooler `search_path` repair.

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

### Data warehouse release path

The warehouse has a dedicated workflow,
[`data-warehouse-production.yml`](../../.github/workflows/data-warehouse-production.yml).
It tests the pinned warehouse submodule, builds a commit-tagged image on a hosted
runner, and deploys its immutable digest on the existing production runner.
[`deploy-data-warehouse.py`](../../scripts/deploy-data-warehouse.py) applies only
warehouse resources, waits for a separate schema Job, then verifies worker
readiness and exact source revision. A failed rollout restores the prior worker
pod specification when available; model/schema rollback is a separate compatible
migration operation.

Warehouse rollout waits for the requested Deployment generation and its updated,
ready, available replica within 480 seconds. It tolerates a stale
`ProgressDeadlineExceeded` condition left by the previous failed generation;
that condition alone is not evidence that the new template failed. Once ready,
the release verifies the worker's exact revision and waits for an acknowledged
batch when real source data is pending.

Workload Identity Federation grants short-lived tokens to separate ingest and
schema identities. No human Google session or service-account key is installed
in the pod. Preserve the checkpoint PVC and inspect pending batch/load job state
before resetting any offsets. Sandbox expiry and the selected billing-disabled
mode remain in effect. Operational details are in the
[warehouse deployment guide](../../data-warehouse/docs/07-continuous-deployment.md).
The latest [verified production receipt](../warehouse-production-status.md)
records the deployed revision, acknowledged real batch, Kafka frontier, and
source-to-mart reconciliation. Reinspect live status after a new release.

The foundation manifest selects the platform envelope stream and a new consumer
group. It preserves legacy raw data and refuses cutover if the legacy durable
journal still has a pending batch. Deploy the source-owned AI export endpoint
before exercising `data-warehouse-ai-snapshot`. Its six-hour UTC CronJob has
`Forbid` concurrency, bounded exports, a separate private state PVC and the same
raw-only ingest identity. Overlapping snapshots skip confirmed unchanged IDs.
Check scheduled Job success separately from the Kafka worker's readiness; a
missing export, failed snapshot or empty raw table is not proof of zero AI use.
Run `data-warehouse/scripts/analyze_foundation.py` with authorized operator CLI
authentication for aggregate source coverage, key uniqueness and relationship
checks. The source register records producer gaps independently of row counts.

The legacy CD path is manual-only. Warehouse-only and documentation-only commits
do not restart application deployments through it.

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

### 3.4 GitHub Actions runner kubeconfig

The production runner is a non-interactive systemd service. It does not source
the operations user's `.bashrc`, so setting `KUBECONFIG` only in that file does
not configure CI/CD. The runner must use a dedicated kubeconfig owned by the
runner user:

```text
/home/bdc_web/.kube/config
```

The systemd service must also contain:

```ini
[Service]
Environment=KUBECONFIG=/home/bdc_web/.kube/config
```

Use `scripts/bootstrap-production-runner.sh` to provision both. Do not make
`/etc/rancher/k3s/k3s.yaml` world-readable. K3s can recreate that root-owned
file on restart and discard ad-hoc mode changes.

Verify the effective service configuration and access with:

```bash
systemctl show <runner-service> -p User -p Environment
sudo -u bdc_web env -i \
  HOME=/home/bdc_web \
  KUBECONFIG=/home/bdc_web/.kube/config \
  PATH=/usr/local/bin:/usr/bin:/bin \
  kubectl get nodes
```

Production workflows run a kubeconfig preflight before modifying image-pull
Secrets or workloads. If that preflight fails, repair the runner configuration;
do not add `sudo kubectl` to workflow steps.

### Flashcard library rollout

AI schema V016/V017 may already be present from a manual migration. The production
workflow detects complete existing schemas and records them, then applies V018 in
one transaction before the new AI image rolls out. A partial schema stops rollout.
After the AI HTTP/worker, LMS and frontend images have rolled out, run
`scripts/check-flashcard-rollout.sh` from this repository with cluster access.
It checks both routes and the required AI columns without reading student data.
A POST 404 can originate from a missing LMS route or from an older AI image;
check the deployed image tags and the route probe before changing migrations.

### Course knowledge map rollout

The AI migration step also applies V023 (`managed_by`, `external_key` and
`metadata` on `knowledge_nodes`, plus the per-course external-key index) before
the AI image rolls out. It is additive and rerunnable. A manually deployed AI
image must not receive `mcp_save_course_knowledge` traffic until V023 is applied,
because the save path selects and writes those columns. After rollout, open an
owned course, call `mcp_course_knowledge_read` with `action="outline"`, then run
`mcp_save_course_knowledge` with `dry_run=true` and inspect the plan before any
confirmed write. Verify coverage increases and `list_knowledge_nodes` returns
the new nodes.

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

## 5. Current CI/CD design - source of truth

Each image has one build owner. Application releases use one automatic rollout
workflow in this repository; a frontend pointer update is part of that rollout.

| Workflow | Trigger | Responsibility |
|---|---|---|
| `.github/workflows/production.yml` | Push to `main`, manual dispatch | Build changed root-owned images; reuse the pinned frontend image; deploy the combined service list once. |
| `.github/workflows/ci.yml` | PR to `main`/`dev`/release, push to `dev`/`develop`/release, manual | Check root-owned services; publish nonproduction branch images where configured. No automatic main push build. |
| `.github/workflows/cd-production.yml` | Manual dispatch only | Emergency restart of existing images, serialized with production releases. |
| Frontend `ci.yml` | PR to `main`/`dev`, push to `dev` | Lint and test-build frontend; superseded checks on the same ref are cancelled. |
| Frontend `cd-dockerhub.yml` | Push to frontend `main` | Build/publish `bdc-frontend:<frontend SHA>` once, with Docker layer caching. The Docker Next.js build includes lint/type checks. No K3s access. |

`frontend-pointer-deploy.yml` was removed. Root CI no longer builds/tests or
publishes the frontend, including when `force_build_all=true`. The dedicated
warehouse workflow remains separate and continues to own its image and rollout.

### 5.1 Primary production pipeline

1. Detect changed services. The matrix covers Auth, AI, Recommender, Personalize,
   LMS, Lab, Chat, Farm and DutyLog. Frontend gitlink changes add `frontend` to
   the service list without adding a Docker build. Workflow-only edits do not
   rebuild application images; release-routing tests run in the detector.
2. Build changed root-owned images on GitHub-hosted runners, tagged with the
   CoreApplication commit SHA (and the existing `latest` compatibility tag).
   AI shares one image across its HTTP and worker deployments.
3. If frontend is selected, verify that its exact gitlink SHA image exists in
   Docker Hub. This check runs alongside backend builds on a hosted runner and
   waits up to 15 minutes for frontend publication. Missing images fail before
   any production mutation; do not substitute `latest` or rebuild in root CI.
4. Deploy the combined explicit service list once on the production runner.
   `IMAGE_TAG` supplies root-owned images; `FRONTEND_IMAGE_TAG` supplies the
   separately published frontend image. The existing database lock, migration
   ordering, pull-secret setup, ingress apply, rollout verification and image
   rollback behavior remain in place. Never cancel an active production rollout
   merely to prioritize a newer commit.

Publish frontend changes to its repository first, then push the updated gitlink
in CoreApplication. A source-repository push alone does not deploy frontend.
For mixed backend/frontend changes, include the pointer in the same root commit
so both are selected by one release. Existing frontend SHA tags remain usable.
No new dispatch token, repository webhook or cluster credential is needed.

### 5.2 No-change, skipped, success, and deployed

| Change | Docker build in root | Production rollout |
|---|---|---|
| Frontend pointer only | None | Frontend only, using the frontend SHA image. |
| LMS + frontend pointer | LMS only | LMS and frontend in one deployment job. |
| Recommender source only | Recommender only | Recommender only. |
| Docs or workflow-only edits | None | None. Routing validation can still run. |
| Manual `image_tag` + explicit `services` | None | Exactly those services with the supplied immutable tag. |

For frontend-only commits, `should_build=false` and an empty build matrix are
expected, but `services=frontend` means the deploy job must still run after image
verification. For no-change commits, `services` is empty and deploy is skipped.
A green detector/CI job alone is not evidence of a production release.

Manual rollback keeps its existing interface: specify an immutable `image_tag`
and an explicit comma-separated `services` list. When that list includes
frontend, the provided tag overrides the current gitlink for frontend too. For
mixed rollbacks whose repositories have different SHAs, run separately for each
image tag. Missing `services` with an explicit tag fails deliberately. A manual
run without a tag still relies on change detection; it does not mean deploy all.

Root quality CI still runs for PRs and development/release branches. It reports
frontend changes as delegated to the source repository and does not initialize
or build that submodule. `force_build_all` applies to root-owned matrix services.
Development image publication never automatically restarts production; production
releases are owned by `production.yml`. Use PR checks before merging to main;
a direct main push uses the production build path, not a second quality workflow.

#### Jev planner and Deep answer configuration

`k3s/base/configmap.yaml` explicitly sets the planner mode (`active`), deadline
(`0.8` seconds), acceptance threshold (`0.97`), and Deep completion limits
(`12` continuation calls, `24000` estimated visible-answer tokens, `4096`
tokens per chunk). Production retains `JEV_ENABLED=true` and explicitly enables
both planner acceleration and lead collaboration. Missing deployment variables
still use the application's conservative `off` defaults; rollback either mode
to `off` without removing the general Jev binding.

Editing `.env.example` does not configure Kubernetes pods. AI HTTP and worker
Deployments import `bdc-config` via `envFrom`. The normal `production.yml` path
detects ConfigMap edits, builds immutable images, applies the ConfigMap through
`scripts/deploy-production.sh`, and rolls selected workloads to the new image
SHA. The shared ConfigMap selects the matching service categories in
the workflow, not just AI. No workflow edit is needed to ship these keys.

Applying only the ConfigMap does not refresh environment variables in existing
pods. A manual dispatch reusing an already deployed image tag may also skip
the image update; explicitly restart affected Deployments when doing a
configuration-only operational rollout. The legacy `cd-production.yml` only
restarts pods and does not apply the changed ConfigMap. The normal CI path does
not import an arbitrary local `.env` file. Per-container environment overrides,
if configured in the running cluster, must be checked separately.

These Deep limits bound automatic continuation; they do not remove provider
context, rate, or connection limits. Verify effective values and actual chat
completion after deployment. A local manifest render does not establish that
the cluster received the change.

#### `cd-production.yml` - legacy restart path

This workflow does not set an image tag or build an image. It calls `kubectl
rollout restart` for one deployment or all known deployments, then asks
Kubernetes to wait up to 180 seconds per target. Its final maintenance step
removes completed pod objects and checks node disk usage. It prunes unused K3s
containerd images only when usage reaches the configured threshold (82% by
default); it does not prune legacy Docker or active K3s storage. A successful
run never means a new commit reached production: it is only a restart of the
image already configured in Kubernetes.

Restart and rollout-status errors now fail the job and stop subsequent restarts.
The same disk preflight gate applies before restarting. After a failure, cleanup
reports disk usage and removes completed pod objects but skips image pruning so
recovery does not incur unnecessary image downloads. Application smoke checks
remain required. Do not run the manual `all` target casually.

The legacy workflow has no `workflow_run` trigger. Manual dispatch is a
restart-only operation, shares the `production` concurrency group, and must be
treated as production-impacting: select one target where possible and inspect
its current image first. Use the SHA-based primary workflow for releases.

| GitHub status or observation | Operational meaning | Required interpretation/action |
|---|---|---|
| **Skipped** Build and **Skipped** Deploy in `production.yml` | No selected production paths changed. | Expected no-op; no release happened. |
| **Success** workflow, but Build is skipped | Detection/manual-tag policy intentionally avoided a build. | Confirm whether Deploy ran and inspect `services` output. |
| **Success** Deploy in `production.yml` | Selected deployments passed rollout status after a SHA update. | Still run service smoke checks and inspect the deployed image. |
| **Success** in legacy CD | Requested restarts passed rollout checks; no new image was selected. | Do not call it a new release; verify application behavior and the configured image. |
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

### Add or rotate the Jev key for AI chat and MCP

Deploy the image containing the gateway-managed System One integration first.
It bootstraps the **OpenCode Zen (Jev decision API)** provider, the
`jev-1.13-free` model, and a `jev_decision` task binding. Check
that `JEV_ENABLED` is `true` in `bdc-config`:

```bash
kubectl -n default get configmap bdc-config -o jsonpath='{.data.JEV_ENABLED}{"\n"}'
kubectl -n default get deployment ai-service -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Sign in as an authorized admin and confirm the OpenCode Zen provider's Base URL
is `https://opencode.ai/zen/v1` under **LMS Admin > LLM Configuration >
Providers**. The gateway appends `/systemone` for Jev. In **API Keys**, choose
that provider and add the Zen API key. In **Models** and **Task bindings**,
confirm `jev-1.13-free` is attached to `jev_decision`. To select a System One
model hosted by another provider, give the new model JSON config
`{"api_protocol":"system_one"}`, configure that provider's HTTPS Base URL and
key, and bind the model to `jev_decision` with the desired priority or pin.
To rotate a key,
add the replacement key and verify it works before disabling or deleting the
old key. The gateway encrypts keys at rest and leases active keys on each Jev
call; no K3s Secret update or pod restart is needed for key changes. Use a
nonprivate example with MCP `assess_question` or a Deep question near the
0.35–0.45 local score band to verify. A 401/403 or 429 is reflected in the
gateway key status; chat keeps its local routing fallback.

If `JEV_ENABLED` is `false`, apply the reviewed production ConfigMap through
the normal deployment path. The Admin key store is the source of truth. If an
earlier rollout put `OPENCODE_API_KEY` in `$HOME/codespace/core/.env`, remove
that entry after the Admin key has passed verification. `prepare-runtime.sh`
imports values from `.env` into `bdc-secrets` even when the Compose service no
longer uses them. Remove the obsolete Secret field only after verifying the
Admin-managed key works:

```bash
if kubectl -n default get secret bdc-secrets -o json |
   jq -e '.data | has("OPENCODE_API_KEY")' >/dev/null; then
  kubectl -n default patch secret bdc-secrets --type=json \
    -p='[{"op":"remove","path":"/data/OPENCODE_API_KEY"}]'
fi
```

Do not place the Zen key in Git or any other K3s Secret.

### 5.3 What `scripts/deploy-production.sh` does

The deploy script is intentionally conservative:

```text
verify kubectl access
  -> disk preflight: prune unused CRI images if needed, then remeasure
  -> stop before rollout if disk usage remains >=82% (configurable)
  -> synchronize runtime configuration and selected infrastructure
  -> record each selected Deployment's current image
  -> render only that Deployment with its final immutable image, then apply
  -> await that Deployment before updating the next workload
  -> on error: restore only images changed by this invocation
```

It does **not** apply the full Kustomize base during each release, so a stale
manifest cannot overwrite unrelated deployment images. It also does not
delete persistent volumes.

`render-deployment.py` uses kubectl's client dry-run JSON plus Python's standard
library, without adding a runner dependency. It accepts both consecutive JSON
objects from multi-document manifests and a Kubernetes List, and rejects invalid
or partial JSON before applying anything. The parent deploy process owns rollback;
inherited command-substitution ERR traps do not roll workloads back twice.
Shared AI manifests cannot apply an
unselected worker or briefly deploy their placeholder image. Farm configuration
annotations accompany the final image in the same template update.

The primary workflow checks disk before credential/schema preparation and the
script rechecks before application rollout. `K3S_PRUNE_DISK_THRESHOLD` defaults
to 82. A missing approved sudo rule or ineffective prune cannot silently bypass
the preflight gate. Image cleanup targets only unused K3s CRI images; it does not
delete active snapshots, model caches, logs, Docker storage or persistent volumes.
Failed/Unknown pod objects are retained for diagnostics, and terminating pods are
not force-deleted automatically. Previous container logs are requested only when
Kubernetes reports a prior terminated container; missing retained logs remain
nonfatal diagnostics. Primary workflow failure cleanup skips image pruning while
rollback/recovery may still be active. A deployment-only script/workflow edit runs
safety tests without rebuilding or rolling out every application image; the new
logic takes effect on the next selected/manual release. These changes do not
repair an already full production filesystem by themselves.

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

### 7.2 Immediate triage - read-only first

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

### 8.1.1 Central service logs and error charts

The versioned [logging stack](../../k3s/logging/README.md) adds Alloy file
collectors, a singleton Kubernetes Events reader and Loki with 72h retention.
It provisions **BDC Logs** and **BDC Service Logs & Errors** on the existing
Grafana at `/monitor/d/bdc-service-logs/`. Service/pod/level/search filters and
error-rate plots include worker logs, while persisted Events show scheduling
and eviction failures that application logs cannot explain.

Run `python3 scripts/enable-service-logs.py` to review the plan, then use
`--apply` from an authorised kubectl/Helm workstation. The installer keeps the
installed `kps` chart version and existing datasources. These files are not
automatically deployed by the application-image workflow. Loki stays internal;
the 5Gi local-path PVC does not enforce a node disk quota. See the linked guide
for storage limits, validation, access restrictions and rollback preserving logs.

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

### P0 - restore reliable smoke and observability

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

### P1 - make CI/CD deterministic and complete

- [x] Consolidate automatic application releases in `production.yml`; keep legacy
      restarts manual-only with the same production concurrency lock.
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
- [x] Cover Auth, Chat and Lab in the production matrix.
- [x] Frontend repository owns image builds; root production reuses its pinned
      image and combines it with other selected deployments.
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

### P2 - operational resilience

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

- [Primary production workflow](../../.github/workflows/production.yml)
- [Quality CI workflow](../../.github/workflows/ci.yml)
- [Deployment script](../../scripts/deploy-production.sh)
- [K3s deployment guide](../../k3s/DEPLOYMENT.md)
- [Performance test assets](../../performance-tests/README.md)
- [Observability manifests](../../k3s/observability/kustomization.yaml)

### Optional lead-agent collaboration

`AGENT_LEAD_MODE=active` is declared in `bdc-config`, Compose and the sample
environment. Deploy the updated code and configuration and roll the AI workload
to load it. Explicit environment overrides still take precedence. This flag is separate from
`JEV_PLANNER_MODE`; the latter is the Standard-mode planner accelerator.
Keep System One disabled via `JEV_ENABLED=false` if its managed binding is not
available; lead planning can still choose LLM and retrieval executors.
Monitor latency, gateway usage and `lead_fallback` events after activation. See [ADR 7](../adr/ADR-7-bounded-lead-agent-collaboration.md).

### Lab authoring worker rollout

AI authoring adds `ai-lab-authoring-worker`, using the same immutable `bdc-ai`
image as AI HTTP. V019 `lab_authoring_jobs` is included in the existing
pre-rollout migration runner. The deployment script applies its selected
manifest and image; no production change is implied by editing these files.
The worker needs AI PostgreSQL and the same `AI_KEY_ENCRYPTION_SECRET` used by
AI HTTP; it does not need embedding warmup, Kafka, Qdrant or Neo4j.

After an approved rollout, verify an authenticated teacher can create and poll
one draft job, the worker transitions it to READY/FAILED, another teacher cannot
read it, and an interrupted lease recovers. Validate the task bindings for
`format_lab`, `create_lab`, `create_lab_testcase`, `edit_testcase` and
`create_lab_generator` in the gateway admin panel. Monitor queue age and worker
logs; READY is a proposal, not publication. Terminal Git labs additionally need
a built and pinned image from `lab-service/sandbox/terminal/Dockerfile`.
Docker build/run remains unavailable on the default terminal runtime.

## Knowledge Farm rollout

The production selector now builds `bdc-farm` for `farm-service/` changes.
Provision the dedicated farm database and `bdc-farm-secrets`, apply the Auth
receipt migration, then roll out Auth, farm and the frontend submodule in that
order. The deploy script creates/waits for the reward topic Job. Consumer
activation is opt-in through `FARM_REWARDS_ENABLED`; missing farm secrets do
not activate it on existing Auth deployments. The base Kustomize farm workload
requires its own secrets before startup. No database is shared with LMS/Auth.
See [canonical deployment/recovery instructions](../features/KNOWLEDGE_FARM.md#rollout-k3s),
including backlog monitoring, replay retention and coordinated event-key rotation.

### Knowledge Farm connection configuration

`gamefarm` and its SQL migrations are provisioned before deployment. Farm
rollout synchronizes its Kubernetes connection Secret from the current shared
Neon credentials, or the optional GitHub `production` secret `FARM_DATABASE_URL`.
It does not create databases/roles or run a migration Job. Select
`auth-service,farm-service` together; configuration revisions reload both pods
when connection settings change, including retries of the same image tag.
See [Knowledge Farm GitHub rollout instructions](../features/KNOWLEDGE_FARM.md#rollout-k3s).

## HPCC AI Gateway (aimodels) rollout

> **Suspended (2026-11-12):** HPCC access is unavailable. Keep the submodule
> and manifests for future reuse, but do not reconnect. Both gateway deployments
> have zero replicas; production CI no longer builds/selects gateway images.
> The deployment script rejects manual gateway selection and scales existing
> gateway/info deployments to zero before rolling out other workloads.
> Stop an existing tunnel immediately on the production context with
> `kubectl -n default scale deployment ai-gateway --replicas=0`.
> This source change must be deployed before CI can enforce suspension.
> The historical setup instructions below are retained only for future reuse.


`ai-gateway` (`ai-gateway/`) routes OpenAI-compatible traffic from
`https://bdc.hpcc.vn/aimodels/*` through one Autossh tunnel to the HPCC GPU
nodes. One pod runs both containers (`tunnel` and `gateway`) sharing
localhost; the tunnel holds the SSH forwards, the gateway probes
`/healthz`/`/readyz` and listens on 8080 behind the `ai-gateway` Service
(port 8090), Traefik Ingress, and a shared public edge (TLS terminates
upstream, never at the gateway).

One-time cluster prerequisites (never in Git). The `.env` file used by local
docker-compose maps 1:1 to these Secret keys: `GATEWAY_API_KEY`,
`SSH_HOST`, `SSH_PORT`, `SSH_USER` (optional upstream keys such as
`VLLM_API_KEY` when a backend uses `api_key_env`):

```bash
kubectl -n default create secret generic ai-gateway-secrets \
  --from-literal=SSH_HOST=<hpcc-login-host> \
  --from-literal=SSH_PORT=<hpcc-login-port> \
  --from-literal=SSH_USER=<hpcc-user> \
  --from-literal=GATEWAY_API_KEY="$(openssl rand -base64 32)" \
  --from-file=ssh_key=/path/to/id_ed25519 \
  --from-file=known_hosts=/path/to/known_hosts \
  --dry-run=client -o yaml | kubectl apply -f -
```

Verify the `known_hosts` fingerprint with the HPCC administrator first.
Anything secret stays in `ai-gateway-secrets`.

The backend inventory in `config.yaml` (GPU node names, internal hosts/ports,
model IDs) is also private infrastructure data. Therefore the full
`ai-gateway-config` ConfigMap is applied out-of-band from the operator's
working copy — the local `ai-gateway/config.yaml` is directly usable because
its `/run/secrets/*` paths match the pod mounts:

```bash
cd ai-gateway
kubectl -n default create configmap ai-gateway-config \
  --from-file=config.yaml=config.yaml \
  --dry-run=client -o yaml | kubectl apply -f -
```

`config.example.yaml` is the public template (only `${VAR}` placeholders);
`k3s/base/ai-gateway-deployment.yaml` references the ConfigMap by name only
and contains no topology data. Create/refresh the ConfigMap and Secret BEFORE
the first rollout; a missing object fails pods with
`CreateContainerConfigError`. Adding a GPU node afterwards is one kubectl
ConfigMap apply plus a pod restart; no image change is required.

Deployment: `main` selects the gateway through the `ai-gateway` path filter in
`production.yml`, which builds two images (`bdc-ai-gateway`,
`bdc-ai-gateway-tunnel`) from `ai-gateway/` and patches both containers on one
rollout (`SERVICES=ai-gateway`). A public marketing page is served at
`https://bdc.hpcc.vn/aimodels/info` (`k3s/base/ai-gateway-info.yaml`): a
standalone nginx pod with a static HTML index ConfigMap plus the BDC logo and
favicon embedded as `binaryData` (copied from `frontend/src/assets/bdclogo.png`,
resized). The page supports light and dark themes, shows no hosts, ports,
credentials or topology, and renders the live model list by calling the
gateway's unauthenticated catalog endpoint `/aimodels/public/models`, which
returns only model IDs, derived capabilities and replica counts. If the
gateway is unreachable the page falls back to a static overview. Its route has
a longer path prefix, so Traefik auto-priority keeps it ahead of the gateway
router. Updating the page is a manifest edit plus a normal push; the pod
consumes an upstream `nginx:1.27-alpine` image and is applied inside the
`ai-gateway` selection only. The `/aimodels` route strips its prefix and rate
limits 120 req/min; gzip is intentionally NOT applied to that route; the info
page has gzip plus a 10-minute cache.

### Private submodule checkout in Actions

CI and production builds check out the root with `submodules: false`, then run
`scripts/checkout-service-submodules.py` with the matrix build context. Only
ancestor/descendant gitlinks required by that context are initialized at their
pinned revisions: frontend for frontend, DutyLog for dutylog/backend, and MCP
skills for ai-service. An unrelated service never clones ai-gateway. Rollout
jobs need only root-owned scripts/manifests and gitlink SHAs, so do not clone
submodules at all.

The default `GITHUB_TOKEN` is scoped to CoreApplication and cannot read another
private repository. For gateway image builds, configure **CoreApplication →
Settings → Secrets and variables → Actions → New repository secret** named
`SUBMODULE_PAT`. Use a fine-grained token with **Resource owner: Big-Data-Club** and selected
repositories CoreApplication, BDCHub---AIGateway, and any other private submodule
needed by the selected build; grant **Contents: Read-only**. Complete organization
approval/SSO requirements where applicable. The token owner must already have
access; storing a token cannot create repository access.

Build checkout uses this secret when present and the default token otherwise.
Gateway builds explicitly stop with instructions if the secret is absent, rather
than silently trying a default token that cannot work. If it exists but checkout
still reports Repository not found, check selected repositories, token expiry,
organization approval/SSO, and that the repo URL and pinned commit exist. A fork PR
without access to secrets cannot build private gateway code. Re-run the failed job
after configuring access; never paste the token into YAML, `.gitmodules`, chat,
or logs. No submodule URL or public/private visibility change is needed.


### GitHub organization management dashboards

The [GitHub observability design](../operations/GITHUB_ORG_OBSERVABILITY.md)
contains seven management views and an interactive synthetic-data preview.
The standalone `scripts/enable-github-grafana.py --org-id 2 --dashboards --apply`
installs the native pack on the VM after the existing Helm operation completes.
The script is local preparation until an operator runs it; an observer/exporter
is not implemented. Open `/monitor/d/bdc-gh-overview?orgId=2` after rollout.
It reuses this Grafana
instance and the existing five-day Prometheus retention, with no additional
history database. Private GitHub data needs a management-only Grafana
organization/datasource boundary and a separate read-only credential; folder
visibility alone is not datasource isolation on OSS. Confirm installed plugin
compatibility and endpoint capabilities before provisioning. Do not put a PAT
in dashboard JSON or use an operational green state for missing permissions.
