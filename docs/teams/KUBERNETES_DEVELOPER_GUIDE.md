# BDC Hub Kubernetes Developer Guide

This guide gives application developers a quick mental model of the BDC Hub
infrastructure and shows how to inspect or start the application on an
**authorised K3s sandbox**. It is not a production deployment procedure. For
production access, releases, rollback, and incidents, use the
[DevOps runbook](DEVOPS_RUNBOOK.md).

## 1. The platform in five minutes

```text
                              Kubernetes node

 Browser ──> Traefik ──> Frontend (Next.js)
                │              │ server-side HTTP
                ├──────────────┼──> Auth       :8080 ──> Auth PostgreSQL
                ├──────────────┼──> LMS        :8081 ──> LMS PostgreSQL
                ├──────────────┼──> Lab        :8082 ──> Lab PostgreSQL
                ├──────────────┼──> Chat       :8083 ──> Chat PostgreSQL
                │              ├──> AI         :8000 ──> AI PostgreSQL
                │              │                    ├──> Qdrant
                │              │                    ├──> Neo4j
                │              │                    └──> object storage
                │              ├──> Personalize :8082
                │              └──> Recommender :8086
                │
                └── public paths are defined in base/ingress.yaml

 Application services <──> Redis (cache/short-lived state)
 Producers ──> Kafka ──> AI workers / Personalize consumers

 Observability: ServiceMonitor ──> Prometheus ──> Grafana
```

There are two layers to keep separate:

| Layer | Kubernetes objects | Responsibility |
|---|---|---|
| Infrastructure | K3s, Traefik, Kafka, Redis, PVC/PV, PostgreSQL, Qdrant, Neo4j, MinIO, Prometheus/Grafana | Networking, scheduling, messaging, cache, storage, metrics, and runtime configuration |
| Application | Frontend, Auth, LMS, Lab, Chat, AI API, AI workers, Personalize, Recommender | Product behaviour, API contracts, authorization, domain data, background work, and user experience |

The infrastructure layer makes an application reachable and gives it runtime
dependencies. It does not own application data rules. Each application service
owns its database and must communicate with another service through an API or a
documented Kafka event-not by querying the other service's database.

## 2. Application layer at a glance

| Workload | Code | Runtime role | Cluster service / port |
|---|---|---|---|
| `frontend` | `frontend/` | Next.js UI and server-side API proxy | `frontend:3001` |
| `auth-service` | `auth-and-management-service/` | Identity, roles, organisations | `auth-service:8080` |
| `lms-service` | `lms-service/` | Courses, content, quizzes, progress | `lms-service:8081` |
| `lab-service` | `lab-service/` | Coding labs and submissions | `lab-service:8082` |
| `chat-service` | `chat-service/` | Chat HTTP/WebSocket state | `chat-service:8083` |
| `ai-service` | `ai-service/` | Synchronous AI/RAG HTTP API | `ai-service:8000` |
| `ai-worker` | `ai-service/` | Kafka-driven indexing and AI jobs | No Service; worker only |
| `course-blueprint-worker` | `ai-service/` | Durable course-blueprint jobs | No Service; worker only |
| `personalize-service` | `personalize-service/` | Learner profiles and analytics | `personalize-service:8082` |
| `recommender-service` | `recommender-service/` | Low-latency recommendations | `recommender-service:8086` |

Kubernetes DNS is the normal service-to-service discovery mechanism. For
example, LMS is reached inside the cluster as `http://lms-service:8081`; a pod
must not depend on another pod's IP address.

## 3. Infrastructure layer at a glance

| Component | Base or profile | Purpose |
|---|---|---|
| K3s | Host runtime | Lightweight Kubernetes distribution; the current production topology is single-node |
| Traefik | K3s / `k3s/ingress/` | External HTTP routing and path middleware |
| Kafka | `k3s/base/` | Durable asynchronous events and job delivery |
| Redis | `k3s/base/` | Cache and short-lived shared state; logical DBs separate consumers |
| AI model cache | `k3s/base/` plus profile storage | Shared PVC used by the AI API and workers |
| Managed data services | `k3s/overlays/serverless/` | Neon PostgreSQL, Qdrant Cloud, Neo4j Aura, and Cloudflare R2 endpoints |
| In-cluster data services | `k3s/overlays/local-db/` | Four PostgreSQL instances, Qdrant, Neo4j, and MinIO for infrastructure testing |
| Monitoring | `k3s/kube-prometheus-stack/`, `k3s/observability/` | Prometheus Operator values, ServiceMonitors, and Grafana dashboards |

### Kubernetes objects used here

| Object | How to read it in this repository |
|---|---|
| `Deployment` | Stateless HTTP services and workers; changing its pod template creates a rollout |
| `StatefulSet` | Kafka, Redis, and local data services that need stable storage identity |
| `Service` | Stable in-cluster DNS name and port in front of pods |
| `Ingress` / Traefik `Middleware` | Public hostname/path routing and path rewrites |
| `ConfigMap` | Non-sensitive runtime configuration and internal service URLs |
| `Secret` | Credentials and signing keys; the real values are created at runtime, not committed |
| `PersistentVolumeClaim` | A workload's request for durable storage |
| `ServiceMonitor` | Tells the Prometheus Operator which application metrics endpoints to scrape |

## 4. Manifest structure and profiles

```text
k3s/
├── base/                    shared applications, Kafka, Redis, ConfigMap, PVC
├── overlays/
│   ├── serverless/          managed-service endpoint overrides and pinned images
│   └── local-db/            optional in-cluster data services
├── ingress/                 separately applied public Traefik routes
├── kube-prometheus-stack/   Helm values for the active monitoring stack
├── observability/           application ServiceMonitors and dashboard
└── monitoring/              legacy/auxiliary manifests; verify before use
```

Kustomize composes a base with one environment profile:

```bash
# Render only; these commands do not contact or change a cluster.
kubectl kustomize k3s/base
kubectl kustomize k3s/overlays/serverless
kubectl kustomize k3s/overlays/local-db
```

Important current constraints:

- `k3s/base` is reusable configuration, not a complete environment. It expects
  a runtime `bdc-secrets` Secret and valid data-service endpoints.
- The serverless overlay is a controlled staging/cutover profile. It sets most
  application replicas to zero. Always inspect rendered replica counts before
  applying or scaling it.
- The local-db overlay adds data workloads, but it does not currently provide a
  Chat PostgreSQL workload or patch every application endpoint to the local
  Services. It is useful for infrastructure work, but is not yet a
  one-command, isolated developer environment.
- Ingress is deliberately separate from the workload overlays. Do not apply it
  to a sandbox until its hostname, DNS, TLS, and exposure have been approved.
- The committed `k3s/base/secrets.yaml` contains placeholders and is not part
  of the base Kustomization. Never replace its placeholders with real secrets
  or commit a generated Secret.

For ordinary feature development, Docker Compose remains the supported local
path. Use Kubernetes when testing manifests, probes, service discovery,
resource behaviour, or an authorised shared environment.

## 5. Quick start: inspect an existing cluster

Prerequisites are `kubectl`, an approved kubeconfig, and access to the intended
namespace. These commands are read-only:

```bash
kubectl config current-context
kubectl cluster-info
kubectl get nodes

kubectl get deployments,statefulsets,services,pvc -n default
kubectl get pods -n default -o wide
kubectl get ingress -n default
kubectl get events -n default --sort-by=.lastTimestamp
```

Before any write, verify that `kubectl config current-context` is the sandbox
you intend to change. If it is production, stop and follow the DevOps runbook.

To inspect one application:

```bash
kubectl describe deployment/lms-service -n default
kubectl logs deployment/lms-service -n default --tail=100
kubectl get deployment/lms-service -n default \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

To access a service without creating public ingress:

```bash
kubectl port-forward -n default service/lms-service 8081:8081
# In a second terminal:
curl --fail http://127.0.0.1:8081/health
```

Useful health endpoints are Auth `/actuator/health`, LMS/Lab/Chat/AI/
Personalize/Recommender `/health`, and Frontend `/api/health`.

## 6. Quick start: start the managed-dependency profile on a sandbox

This section changes cluster state. Use it only on a disposable or approved
sandbox; production releases go through CI/CD.

### Prerequisites

- A working K3s/Kubernetes node and `kubectl` context
- The repository checked out on the operator machine
- Docker Compose available locally (the preparation script uses its `.env`
  parser; it does not start Compose containers)
- Approved sandbox credentials for PostgreSQL, Qdrant, Neo4j, R2, LLM APIs,
  and the image registry
- The AI model-cache host path/PV provisioned by the platform owner

### 1. Prepare runtime configuration

Create `.env` from the example and fill every required sandbox value. Do not
use production credentials and do not commit the file.

```bash
cp .env.example .env
# Edit .env with sandbox values, then confirm it remains ignored by Git.
git check-ignore .env
```

The preparation script validates required keys and creates or updates
`bdc-secrets`, `bdc-env-overrides`, and the registry pull secret in `default`:

```bash
BDC_NAMESPACE=default ./k3s/scripts/prepare-runtime.sh "$PWD/.env"
kubectl get secret/bdc-secrets configmap/bdc-env-overrides -n default
```

Do not print or decode the Secret as part of routine verification.

### 2. Render and review

```bash
kubectl kustomize k3s/overlays/serverless > /tmp/bdc-serverless.yaml
kubectl apply --dry-run=server -f /tmp/bdc-serverless.yaml
kubectl diff -f /tmp/bdc-serverless.yaml
```

Review the target namespace, image digests, replica counts, endpoint hosts,
storage objects, and diff. `kubectl diff` can return exit code `1` when a diff
exists; that does not by itself mean rendering failed.

### 3. Apply infrastructure and staged workloads

```bash
kubectl apply -k k3s/overlays/serverless
kubectl get pods,pvc -n default
```

The overlay intentionally leaves most application deployments at zero. Kafka,
Redis, and any workload not covered by the overlay's replica rules may start,
so verify actual state instead of assuming the namespace is idle.

### 4. Start the application layer explicitly

```bash
kubectl scale -n default \
  deployment/auth-service \
  deployment/lms-service \
  deployment/lab-service \
  deployment/chat-service \
  deployment/ai-service \
  deployment/ai-worker \
  deployment/course-blueprint-worker \
  deployment/personalize-service \
  deployment/recommender-service \
  deployment/frontend \
  --replicas=1

kubectl get pods -n default --watch
```

AI pods can take longer on their first start while the embedding/reranker
models populate the shared cache. In another terminal, check rollouts and
events rather than repeatedly restarting them:

```bash
kubectl rollout status deployment/auth-service -n default --timeout=5m
kubectl rollout status deployment/lms-service -n default --timeout=5m
kubectl rollout status deployment/ai-service -n default --timeout=12m
kubectl get events -n default --sort-by=.lastTimestamp
```

Use port-forwarding for sandbox access. Apply `k3s/ingress/` only as an
approved cutover step after DNS and exposure are correct.

### 5. Pause application compute

To stop application pods while retaining Kafka, Redis, configuration, and
persistent data for later use:

```bash
kubectl scale -n default \
  deployment/auth-service \
  deployment/lms-service \
  deployment/lab-service \
  deployment/chat-service \
  deployment/ai-service \
  deployment/ai-worker \
  deployment/course-blueprint-worker \
  deployment/personalize-service \
  deployment/recommender-service \
  deployment/frontend \
  --replicas=0
```

This does not stop StatefulSets or delete PVC data. Environment teardown is a
separate, potentially destructive operation and must follow the sandbox
owner's retention procedure.

## 7. How a request moves through the system

Example: a learner opens a course and triggers AI-assisted processing.

1. Traefik routes `/` to Frontend and `/lmsapiv1/...` to LMS.
2. Traefik middleware rewrites the LMS public prefix to `/api/v1/...`.
3. LMS validates the JWT issued by Auth and reads only the LMS database.
4. A long-running processing request is published to Kafka instead of blocking
   the HTTP request.
5. An AI worker consumes the event, uses the AI database/vector/object stores,
   and publishes or persists the result according to the event contract.
6. Personalize consumes learning events to update learner-facing signals;
   Recommender serves a fast recommendation slate.
7. Each workload exposes health/probe endpoints; Prometheus discovers metrics
   through ServiceMonitors and Grafana visualises them.

This flow explains the main debugging order: ingress, Service/endpoints, pod
readiness, application logs, then the specific database/cache/broker dependency.

## 8. Fast troubleshooting map

| Symptom | First checks |
|---|---|
| `Pending` pod | `kubectl describe pod`, PVC binding, node CPU/memory |
| `ImagePullBackOff` | Image name/digest and `dockerhub-registry` pull secret |
| `CreateContainerConfigError` | Missing `bdc-secrets` key or ConfigMap |
| `CrashLoopBackOff` | Current and previous logs: `kubectl logs POD --previous` |
| `0/1 Ready` | Readiness/startup probe path, dependency reachability, startup time |
| Service cannot be reached | Service selector, `kubectl get endpoints`, target port |
| Public path fails but port-forward works | Ingress rule, Traefik middleware, DNS/TLS |
| Worker is idle | Kafka broker readiness, topic/group, credentials, consumer logs |
| AI startup is slow | Model-cache PVC state, download logs, memory limits; do not restart-loop it |

Typical focused commands:

```bash
kubectl get pod -n default
kubectl describe pod/<pod-name> -n default
kubectl logs pod/<pod-name> -n default --all-containers --tail=200
kubectl get service/lms-service endpoints/lms-service -n default -o wide
kubectl top pods -n default
```

## 9. Rules for application changes

- Change application code in the owning service directory and deployment
  behaviour in its matching `k3s/base/*-deployment.yaml`.
- Keep ConfigMaps non-sensitive. Add secrets through the approved runtime
  mechanism; never put a real value in Git.
- Define CPU/memory requests and limits, startup/readiness/liveness behaviour,
  and a stable Service port for every new HTTP workload.
- Treat Kafka as at-least-once delivery: consumers must be idempotent and
  producers must use stable keys.
- Use immutable image SHAs for releases. A successful image build is not a
  deployment until Kubernetes rollout and smoke checks pass.
- Render all affected Kustomize profiles and include ingress, monitoring,
  storage, and rollout implications in the pull request.

Minimum manifest checks:

```bash
kubectl kustomize k3s/base > /tmp/bdc-base.yaml
kubectl kustomize k3s/overlays/serverless > /tmp/bdc-serverless.yaml
kubectl kustomize k3s/overlays/local-db > /tmp/bdc-local-db.yaml
git diff --check
```

Continue with the [Developer guide](DEVELOPER_GUIDE.md) for service-level work
and the [Data platform guide](DATA_PLATFORM.md) before changing Kafka events,
analytics, learner profiles, or recommendations.
