# BDC Hub — System Architecture & Kubernetes Configuration

## Overview

BDC Hub is a **microservices-based Learning Management System (LMS)** deployed on Kubernetes using a serverless-hybrid architecture. Application services run inside the Kubernetes cluster while stateful data (databases, object storage, vector store, knowledge graph) is delegated to managed cloud providers.

---

## Repository Layout

```
bdc/
├── CoreApplication/          # Main microservices monorepo
│   ├── auth-and-management-service/  # Java Spring Boot — Auth & User Management
│   ├── lms-service/                  # Go — Course, Content, and Learning API
│   ├── lab-service/                  # Go — Coding Lab & Exercise API
│   ├── chat-service/                 # Go — Real-time WebSocket Chat API
│   ├── ai-service/                   # Python FastAPI — AI / RAG / Embedding API
│   ├── personalize-service/          # Python — Personalized Recommendations
│   ├── frontend/                     # Next.js — Web UI (bundled inside monorepo)
│   ├── docker-compose.yml            # Full local stack (self-hosted databases)
│   └── docker-compose.serverless.yml # Hybrid stack (external managed databases)
├── BDCHub---Frontend/        # Standalone Next.js frontend (separate repo/deploy)
├── BDCHub---Monitoring/      # Prometheus + Grafana + k6 performance tests
├── Backup-and-Migration-DB/  # Apache Airflow DAGs for DB migration
└── k8s/                      # Kubernetes manifests (this repo)
    ├── base/                 # Stateless application workloads
    ├── overlays/
    │   ├── local-db/         # Overlay: self-hosted databases inside K8s
    │   └── serverless/       # Overlay: external managed database endpoints
    └── monitoring/           # Prometheus, Grafana, Node Exporter
```

---

## Architecture Diagram

```
                           ┌─────────────────────────────────────────┐
  Internet / VPN           │          K3s Kubernetes Cluster           │
       │                   │           (VM: 10.1.8.133)               │
       ▼                   │                                           │
  ┌─────────┐  :80/:443    │  ┌─────────────────────────────────────┐ │
  │  Traefik│◄─────────────┤  │        Ingress + Middlewares         │ │
  │ Ingress │              │  │  Path Routing + Strip/Rewrite Prefix │ │
  └────┬────┘              │  └─────────────────────────────────────┘ │
       │                   │                    │                      │
       │  Routes by Path   │      ┌─────────────┼──────────────┐      │
       ▼                   │      ▼             ▼              ▼      │
  /           → frontend   │  ┌──────┐   ┌──────────┐  ┌──────────┐  │
  /apiv1      → auth-svc   │  │Next.js│   │auth-svc  │  │ lms-svc  │  │
  /uploads    → auth-svc   │  │:3001  │   │:8080     │  │:8081     │  │
  /lmsapiv1   → lms-svc    │  └──────┘   └──────────┘  └──────────┘  │
  /files      → lms-svc    │                   │              │        │
  /labapiv1   → lab-svc    │      ┌────────────┼──────────────┼──┐    │
  /chatapiv1  → chat-svc   │      ▼            ▼              ▼  ▼   │
  /personalize→ personalize│  ┌────────┐ ┌─────────┐ ┌──────┐ ┌────┐ │
  /monitor    → grafana    │  │lab-svc │ │chat-svc │ │ai-svc│ │per-│ │
               (port 3000) │  │:8082   │ │:8083    │ │:8000 │ │-svc│ │
                           │  └────────┘ └─────────┘ └──┬───┘ └────┘ │
                           │                             │             │
                           │   ┌─────────────────────┐  │             │
                           │   │  Internal Infra      │◄─┘             │
                           │   │  kafka-service:9092  │               │
                           │   │  redis-service:6379  │               │
                           │   └─────────────────────┘               │
                           └─────────────────────────────────────────┘
                                         │
                           External Managed Services (SaaS)
                           ┌─────────────┬──────────────┬────────────┐
                           │ Neon Postgres│ Qdrant Cloud │ Neo4j Aura │
                           │  (5 DBs)    │ (Vector DB)  │(Graph DB)  │
                           └─────────────┴──────────────┴────────────┘
                                         │
                           ┌─────────────┴────────────────────────────┐
                           │  Cloudflare R2 (Object Storage / MinIO)  │
                           └──────────────────────────────────────────┘
```

---

## Services

### Application Services (Kubernetes Deployments)

| Service | Language | Port | Role |
|---------|----------|------|------|
| `frontend` | Next.js 14 | 3001 | Web UI — SSR pages, API proxy, NextAuth |
| `auth-service` | Java Spring Boot 3 | 8080 | Authentication, user management, JWT issuance |
| `lms-service` | Go (Gin) | 8081 | Courses, lessons, quizzes, content, file serving |
| `lab-service` | Go (Gin) | 8082 | Coding labs, exercises, sandboxed execution |
| `chat-service` | Go (Gin) | 8083 | Real-time WebSocket chat, message persistence |
| `ai-service` | Python FastAPI | 8000 | RAG pipeline, embedding, quiz generation, LLM API |
| `ai-worker` | Python (Kafka) | — | Background worker: indexes content, processes Kafka events |
| `personalize-service` | Python | 8082 | User personalization recommendations engine |

### Infrastructure Services (Kubernetes StatefulSets — inside cluster)

| Service | Image | Port | Role |
|---------|-------|------|------|
| `kafka` | bitnamilegacy/kafka:3.7.0 | 9092 | Event streaming (KRaft mode, single broker) |
| `redis` | redis:7.2-alpine | 6379 | Cache, session store, Celery broker (DB 0–3 partitioned by service) |

### External Managed Services (Serverless Overlay only)

| Service | Provider | Role |
|---------|----------|------|
| Auth DB | Neon PostgreSQL | `POSTGRES_HOST` — user accounts, roles |
| LMS DB | Neon PostgreSQL | `LMS_POSTGRES_HOST` — courses, content |
| Lab DB | Neon PostgreSQL | `LAB_POSTGRES_HOST` — exercises, submissions |
| Chat DB | Neon PostgreSQL | `CHAT_POSTGRES_HOST` — chat history |
| AI DB | Neon PostgreSQL | `AI_POSTGRES_HOST` — AI conversation state |
| Vector DB | Qdrant Cloud | `QDRANT_URL` — course content embeddings |
| Knowledge Graph | Neo4j Aura | `NEO4J_URI` — course knowledge relationships |
| Object Storage | Cloudflare R2 | `R2_ENDPOINT` — media files, documents |

### Monitoring Services (Separate Kustomize stack)

| Service | Image | Port | Role |
|---------|-------|------|------|
| `prometheus` | prom/prometheus:v2.52.0 | 9090 | Time-series metrics collection |
| `grafana` | grafana/grafana:10.4.2 | 3000 | Metrics visualization, dashboards |
| `node-exporter` | prom/node-exporter:v1.8.1 | 9100 | Host hardware metrics (CPU, RAM, Disk, Network) |

---

## Ingress Routing (Traefik — K3s Built-in)

K3s ships Traefik as its default Ingress Controller. All external traffic enters on port 80/443 and is routed based on path prefix:

| Path Prefix | Target Service | Middleware Applied |
|-------------|----------------|--------------------|
| `/apiv1/*` | `auth-service:8080` | `strip-apiv1` (strips prefix), `compress` |
| `/uploads/*` | `auth-service:8080` | `uploads-cache` (Cache-Control immutable) |
| `/lmsapiv1/*` | `lms-service:8081` | `rewrite-lms` (`/lmsapiv1/X` → `/api/v1/X`), `compress` |
| `/files/*` | `lms-service:8081` | `rewrite-files` (`/files/X` → `/api/v1/files/serve/X`), `files-cache` |
| `/labapiv1/*` | `lab-service:8082` | `rewrite-lab` (`/labapiv1/X` → `/api/v1/X`), `compress` |
| `/chatapiv1/*` | `chat-service:8083` | `rewrite-chat` (`/chatapiv1/X` → `/api/v1/X`), `compress` |
| `/personalize/*` | `personalize-service:8082` | — |
| `/personalize-dashboard/*` | `personalize-service:8082` | — |
| `/monitor/*` | `grafana-service:3000` | — |
| `/` | `frontend:3001` | `compress` |

---

## Data Flow

### User Authentication Flow
```
Browser → /apiv1/auth/** → Ingress (strip /apiv1) → auth-service:8080 → Neon Auth DB
                                                                       → JWT returned
Browser stores JWT and passes it in Authorization header for all subsequent requests
```

### LMS Content Request Flow
```
Browser → /lmsapiv1/courses → Ingress (rewrite → /api/v1/courses) → lms-service:8081
                                                                   → Neon LMS DB
                                                                   → Redis cache (DB 0)
```

### AI RAG Pipeline Flow
```
User asks question → chat-service → Kafka topic → ai-worker (consumer)
                                                    → Qdrant (vector search)
                                                    → Neo4j (knowledge graph)
                                                    → Neon AI DB
                                                    → Groq API (LLM inference)
                                                    → response published back via Kafka
```

### File Upload Flow
```
User uploads file → lms-service:8081 → Cloudflare R2 (S3-compatible)
User requests file → /files/[path] → Ingress → lms-service /api/v1/files/serve/[path]
                                              → R2 presigned URL redirect (cached immutably)
```

---

## Kubernetes Configuration Structure

```
k8s/
├── base/                          # Applied to both overlays
│   ├── configmap.yaml             # Non-sensitive env vars (service URLs, pool sizes, flags)
│   ├── secrets.yaml               # Base64-encoded sensitive credentials template
│   ├── ingress.yaml               # Traefik Ingress + 8 Middleware CRDs
│   ├── kafka-statefulset.yaml     # Kafka KRaft StatefulSet + 2 Services
│   ├── redis-deployment.yaml      # Redis StatefulSet + Service
│   ├── auth-service-deployment.yaml
│   ├── lms-service-deployment.yaml
│   ├── lab-service-deployment.yaml
│   ├── chat-service-deployment.yaml
│   ├── ai-service-deployment.yaml  # Contains both ai-service + ai-worker Deployments
│   ├── personalize-service-deployment.yaml
│   ├── frontend-deployment.yaml
│   └── kustomization.yaml
├── overlays/
│   ├── local-db/                  # Adds self-hosted DB StatefulSets
│   │   ├── postgres-auth-deployment.yaml
│   │   ├── postgres-lms-deployment.yaml
│   │   ├── postgres-lab-deployment.yaml
│   │   ├── postgres-ai-deployment.yaml
│   │   ├── qdrant-deployment.yaml
│   │   ├── neo4j-deployment.yaml
│   │   ├── minio-deployment.yaml
│   │   └── kustomization.yaml
│   └── serverless/                # Overrides DB hosts → external SaaS
│       ├── configmap-serverless.yaml
│       └── kustomization.yaml
└── monitoring/                    # Independent monitoring stack
    ├── prometheus.yaml             # ConfigMap + Deployment + Service
    ├── grafana.yaml                # 2× ConfigMaps + Deployment + Service
    ├── node-exporter.yaml          # DaemonSet + Service
    └── kustomization.yaml
```

---

## Environment Configuration

Application configuration is split into:

- **ConfigMap (`bdc-config`)** — Non-sensitive settings. Automatically loaded via `envFrom` in all Deployments. Includes service discovery URLs, pool sizes, feature flags, ML model names.
- **Secret (`bdc-secrets`)** — Sensitive credentials. Each sensitive value is loaded individually via `valueFrom.secretKeyRef`. Values must be Base64-encoded.

### Redis Database Assignment

Redis is shared across services, partitioned by database number:

| Service | Redis DB |
|---------|----------|
| `lms-service` | DB 0 |
| `ai-service` / `ai-worker` | DB 1 |
| `lab-service` | DB 2 |
| `chat-service` | DB 3 |

---

## Key Design Decisions

1. **K3s over full K8s** — K3s runs on a single VM with minimal RAM overhead (~512 MB), bundles Traefik as the default Ingress Controller, and sets up `kubectl` automatically. Ideal for lab environments.

2. **ai-worker is a separate Deployment with no Service** — It only consumes Kafka events and does not expose an HTTP port. This matches the Docker Compose `command: python -m app.worker.kafka_worker` pattern.

3. **Shared memory for AI workloads** — Both `ai-service` and `ai-worker` mount an `emptyDir` volume with `medium: Memory` at `/dev/shm` (1Gi). PyTorch and sentence-transformers require large shared memory for tensor operations. K8s limits `/dev/shm` to 64MB by default, which causes OOM crashes without this override.

4. **Thread count suppression** — `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `TOKENIZERS_PARALLELISM=false` prevent ML libraries from spawning OS threads beyond the Pod's CPU limit, which causes kernel-level CPU thrashing on shared nodes.

5. **GOMAXPROCS tuning for Go** — All Go services set `GOMAXPROCS=2` matching their `limits.cpu: 2.0`. Without this, Go's runtime reads the host's total CPU count and creates excessive goroutine schedulers.

6. **JVM container awareness** — The Java `auth-service` is built with `jdeps`+`jlink` to produce a custom minimal JRE. At runtime, `-XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0` tells the JVM to derive its heap from the Pod's memory limit, not the host's RAM.
