# BDC Hub — CoreApplication

| Field   | Value        |
|---------|--------------|
| Version | 2.1.0        |
| Status  | Production   |
| Updated | 2026-07-20   |
| Authors | BDC Team     |

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Services](#services)
- [Request Routing](#request-routing)
- [Data Storage](#data-storage)
- [AI Pipeline](#ai-pipeline)
- [Quick Start — Local (Full Stack)](#quick-start--local-full-stack)
- [Serverless Mode (Cloud DBs)](#serverless-mode-cloud-dbs)
- [Environment Variables Reference](#environment-variables-reference)
- [API Documentation](#api-documentation)
- [Developer Notes](#developer-notes)
- [Contributing](#contributing)

---

## Overview

**BDC Hub CoreApplication** is the backend monorepo for an AI-powered Learning Management System. It is composed of six independently deployable microservices communicating over HTTP and Kafka, fronted by a **Traefik reverse proxy** and a **Next.js 14** web application.

The platform goes beyond traditional course management: it runs an **Event-Driven AI Pipeline** that indexes course materials asynchronously, builds a **Knowledge Graph** of learning concepts, and serves **RAG-based semantic search**, **automated quiz generation**, and **spaced-repetition flashcards** — all without blocking the user request path.

---

## Architecture

```
                        ┌─────────────────────────────────────────────────────┐
                        │               Docker / K8s Cluster                  │
 Browser / Client       │                                                     │
        │               │   ┌─────────────────────────────────────────────┐   │
        │  Port 3000    │   │       Traefik v3 — Reverse Proxy            │   │
        └──────────────►│   │  Path-based routing + Middleware rewrites   │   │
                        │   └───────────────────┬─────────────────────────┘   │
                        │                       │                             │
                        │        ┌──────────────┼──────────────────────┐      │
                        │        │              │                       │      │
                        │   /    ▼    /apiv1    ▼     /lmsapiv1        ▼      │
                        │ ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
                        │ │ Next.js  │  │  Auth Service │  │  LMS Service  │  │
                        │ │ Frontend │  │ Spring Boot 3 │  │    Go/Gin     │  │
                        │ │  :3001   │  │    :8080      │  │    :8081      │  │
                        │ └──────────┘  └──────┬───────┘  └──────┬────────┘  │
                        │                      │                  │            │
                        │    /labapiv1 ▼        │                  │            │
                        │ ┌───────────────┐    │ JWT Verify       │ Kafka      │
                        │ │  Lab Service  │    │ User Sync        │ Events     │
                        │ │    Go/Gin     │    │                  │            │
                        │ │    :8082      │    │    /chatapiv1 ▼  │            │
                        │ └───────────────┘  ┌─────────────────┐ │            │
                        │                    │  Chat Service   │ │            │
                        │                    │    Go/Gin       │ │            │
                        │  /personalize ▼    │    :8083        │ │            │
                        │ ┌───────────────┐  └─────────────────┘ │            │
                        │ │  Personalize  │                       │            │
                        │ │   Service     │   ┌───────────────────┘            │
                        │ │   Python      │   │  Kafka  ◄──────────────────┐  │
                        │ │    :8082      │   │ :9092   │   ai-service      │  │
                        │ └───────────────┘   └────┬────┘   events /        │  │
                        │                          │        index requests   │  │
                        │                          ▼                         │  │
                        │                   ┌──────────────┐  ┌──────────┐  │  │
                        │                   │  AI Worker   │  │AI Service│  │  │
                        │                   │ Kafka Consumer│  │ FastAPI  │  │  │
                        │                   │   Python     │  │  :8000   │  │  │
                        │                   └──────────────┘  └──────────┘  │  │
                        └─────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Frontend | Next.js, TypeScript, NextAuth.js | 14+ |
| Auth Service | Spring Boot, Spring Security, JWT | 3.x (Java 21) |
| LMS Service | Go, Gin framework, GORM | 1.21+ |
| Lab Service | Go, Gin framework | 1.21+ |
| Chat Service | Go, Gin framework, WebSocket | 1.21+ |
| AI Service | Python, FastAPI | 3.10+ |
| AI Worker | Python, Kafka Consumer | 3.10+ |
| Personalize Service | Python | 3.10+ |
| Message Broker | Kafka (KRaft, no ZooKeeper) | 3.7.0 |
| Reverse Proxy | Traefik | v3.6 |
| Relational DB | PostgreSQL (4 separate databases) | 15 |
| Vector Store | Qdrant (gRPC + REST) | v1.13.6 |
| Knowledge Graph | Neo4j (with APOC plugin) | 5.26 |
| Cache / Session | Redis | 7 (alpine) |
| Object Storage | MinIO (or Cloudflare R2 in serverless mode) | latest |

---

## Services

### Frontend — Next.js 14
- **Port:** 3001 (internal), exposed via Traefik on port 3000
- **Role:** SSR web UI, NextAuth session handling, server-side API proxying to microservices
- **Connects to:** `auth-service:8080`, `lms-service:8081`, `ai-service:8000`, `chat-service:8083`
- **Build args:** `NEXT_PUBLIC_GOOGLE_CLIENT_ID`, `NEXT_PUBLIC_CHAT_WS_URL` are baked in at build time

### Auth Service — Spring Boot 3 (Java 21)
- **Port:** 8080
- **Role:** User registration/login, JWT issuance and validation, role-based access control, Google OAuth, admin bootstrap, cross-service user synchronization (push to LMS and Chat via API)
- **DB:** PostgreSQL (`POSTGRES_*`)
- **Storage:** Local volume `upload_data:/app/uploads` (user avatars, attachments)
- **Notable:** Exposes `/actuator/prometheus` for Prometheus scraping. Uses HikariCP connection pool with tunable `HIKARI_MAX_POOL_SIZE`.

### LMS Service — Go/Gin
- **Port:** 8081
- **Role:** Courses, lessons, quizzes, enrollments, forums, progress tracking, file storage (MinIO/R2), learning analytics
- **DB:** PostgreSQL (`LMS_POSTGRES_*`)
- **Cache:** Redis DB 0
- **Storage:** MinIO bucket `lms-files` (or Cloudflare R2 in serverless mode)
- **Notable:** Publishes Kafka events on content upload so `ai-worker` can index new documents automatically. Tuned with `GOMAXPROCS=2`.

### Lab Service — Go/Gin
- **Port:** 8082
- **Role:** Coding exercises, lab assignments, student submission management
- **DB:** PostgreSQL (`LAB_POSTGRES_*`)
- **Cache:** Redis DB 2
- **Storage:** MinIO bucket `lab-files` (separate bucket from LMS)

### Chat Service — Go/Gin
- **Port:** 8083
- **Role:** Real-time WebSocket chat rooms, message persistence, presence tracking
- **DB:** PostgreSQL (`CHAT_POSTGRES_*`) — uses SSL (`require`) even in local docker stack
- **Cache:** Redis DB 3 with aggressive pool settings (`REDIS_POOL_SIZE=100`) for WebSocket fan-out

### AI Service — FastAPI (Python)
- **Port:** 8000
- **Role:** User-facing AI API — RAG question answering, semantic document search, quiz generation, flashcard generation, knowledge graph queries
- **DB:** PostgreSQL (`AI_POSTGRES_*`), Qdrant (vector store), Neo4j (knowledge graph)
- **Cache:** Redis DB 1
- **Model:** `BAAI/bge-m3` for embeddings (1024 dimensions), `BAAI/bge-reranker-v2-m3` for reranking (enabled on `ai-service`, disabled on `ai-worker` to save RAM)
- **LLM:** Groq API — `llama-3.1-8b-instant` (chat), `llama-3.3-70b-versatile` (quiz generation)
- **Important:** Requires `shm_size: 1gb` — PyTorch multiprocessing crashes on the default 64 MB `/dev/shm`

### AI Worker — Kafka Consumer (Python)
- **Port:** none (no HTTP server)
- **Role:** Background event processor — listens to Kafka topics for `document.uploaded`, `video.added`, etc.; runs embedding pipeline; upserts chunks into Qdrant; builds Neo4j graph nodes
- **Same image as AI Service** but overrides the entry command: `python -m app.worker.kafka_worker`
- **`USE_RERANKER=false`** — reranker model disabled to conserve RAM (worker handles batch ops, not interactive search)
- **Resource allocation:** 4 GB RAM limit (model + batch embedding + Kafka buffers)

### Personalize Service — Python
- **Port:** 8082
- **Role:** Computes personalized course recommendations per user based on learning history and interaction events consumed from Kafka
- **Storage:** `personalize_data:/app/data` — recommendation model state

---

## Request Routing

All external traffic enters through **Traefik** on port 3000 (local Docker) or port 80/443 (production K8s). Traefik applies path-based routing and middleware transformations before forwarding to the target service.

| Incoming Path | Middleware Applied | Target Service | Effective Path |
|--------------|-------------------|----------------|----------------|
| `/` | compress | `frontend:3001` | `/` |
| `/apiv1/**` | `strip-apiv1`, compress | `auth-service:8080` | `//**` |
| `/uploads/**` | `Cache-Control: immutable` | `auth-service:8080` | `/uploads/**` |
| `/lmsapiv1/**` | `rewrite: /lmsapiv1/X → /api/v1/X`, compress | `lms-service:8081` | `/api/v1/**` |
| `/files/**` | `rewrite: /files/X → /api/v1/files/serve/X`, `Cache-Control: immutable` | `lms-service:8081` | `/api/v1/files/serve/**` |
| `/labapiv1/**` | `rewrite: /labapiv1/X → /api/v1/X`, compress | `lab-service:8082` | `/api/v1/**` |
| `/chatapiv1/**` | `rewrite: /chatapiv1/X → /api/v1/X`, compress | `chat-service:8083` | `/api/v1/**` |
| `/personalize/**` | — | `personalize-service:8082` | `/personalize/**` |
| `/personalize-dashboard/**` | — | `personalize-service:8082` | `/personalize-dashboard/**` |

> **WebSocket (Chat):** The Next.js frontend opens WebSocket connections directly to `wss://bdc.hpcc.vn/chatapiv1`. Traefik transparently proxies `Upgrade` requests.

---

## Data Storage

### PostgreSQL — 4 Isolated Databases

Each service owns its schema independently. Databases never share tables.

| Database | Variable Prefix | Owner Service | Notes |
|----------|----------------|---------------|-------|
| `auth` (or `POSTGRES_DB`) | `POSTGRES_*` | Auth Service | Users, roles, OAuth tokens |
| `lms` (or `LMS_POSTGRES_DB`) | `LMS_POSTGRES_*` | LMS Service | Courses, enrollments, progress |
| `lab` (or `LAB_POSTGRES_DB`) | `LAB_POSTGRES_*` | Lab Service | Exercises, submissions |
| `ai` (or `AI_POSTGRES_DB`) | `AI_POSTGRES_*` | AI Service / Worker | AI conversations, session state |
| `chat` (or `CHAT_POSTGRES_DB`) | `CHAT_POSTGRES_*` | Chat Service | Chat rooms, messages |

> Chat DB requires `DB_SSL_MODE: require` even in local Docker since it was designed with Neon (serverless Postgres) as the primary target.

### Redis — 4 Logical Databases

A single Redis instance is shared, partitioned by database number:

| DB Number | Consumer | Purpose |
|-----------|----------|---------|
| 0 | LMS Service | Course/content cache, session data |
| 1 | AI Service + AI Worker | Embedding job locks, rate limiting, AI session cache |
| 2 | Lab Service | Exercise result cache |
| 3 | Chat Service | WebSocket pub/sub, presence tracking, message fan-out |

### Qdrant — Vector Store

- **Collections:** `document_chunks` (1024d, cosine), `knowledge_nodes` (1024d, cosine)
- **Protocol:** gRPC (`QDRANT_GRPC_PORT=6334`) for batch upserts from `ai-worker`; REST for health checks
- **Config:** `QDRANT__STORAGE__ON_DISK_PAYLOAD=true` keeps HNSW graph in RAM while payloads spill to disk

### Neo4j — Knowledge Graph

- **Purpose:** Stores intra-course and cross-course concept relationships (`PREREQUISITE`, `EXTENDS`, `EQUIVALENT`, `RELATED_TO`)
- **Plugin:** APOC (Advanced Procedures and Functions)
- **Bolt protocol** used by `ai-service` for Cypher queries

### MinIO / Cloudflare R2 — Object Storage

- **Local mode:** MinIO container, bucket `lms-files`
- **Serverless mode:** Cloudflare R2 via S3-compatible API (`R2_ENDPOINT`)
- **Lab service** uses a **separate** bucket (`lab-files`) configured independently via `LAB_MINIO_*`

---

## AI Pipeline

The AI pipeline is fully event-driven. No user request blocks on indexing or embedding.

```
Teacher uploads PDF/video to LMS
        │
        ▼
lms-service saves file to MinIO/R2
        │
        ▼
lms-service publishes Kafka event:
  topic: document.uploaded / video.added
  payload: { course_id, node_id, file_path, file_type }
        │
        ▼
ai-worker (Kafka Consumer) receives event
        │
        ├─► PDF: extract text → chunk (size=500, overlap=50)
        │         → embed with BAAI/bge-m3 (1024d)
        │         → upsert into Qdrant collection: document_chunks
        │
        ├─► Video: download → transcribe (Whisper or YouTube fallback)
        │          → chunk transcript
        │          → embed → upsert into Qdrant
        │
        └─► Build knowledge graph nodes in Neo4j
            (link concepts: PREREQUISITE, EXTENDS, RELATED_TO)

Later — Student asks a question:
        │
        ▼
ai-service receives HTTP request (via /lmsapiv1 or frontend proxy)
        │
        ├─► Embed query with BAAI/bge-m3
        ├─► Vector search in Qdrant (top-K chunks)
        ├─► Rerank with BAAI/bge-reranker-v2-m3 (on ai-service only)
        ├─► Graph query Neo4j for related concepts
        ├─► Build context prompt → call Groq API (llama-3.1-8b-instant)
        └─► Return response with source citations
```

### AI Service vs AI Worker — Resource Split

| | `ai-service` | `ai-worker` |
|--|---|---|
| Role | Handles interactive user requests | Processes background indexing jobs |
| HTTP server | Yes (FastAPI :8000) | No |
| USE_RERANKER | `true` | `false` (saves ~400 MB RAM) |
| RAM limit | 1.5 GB | 4 GB |
| CPU limit | 1.5 cores | 3.0 cores |
| OMP_NUM_THREADS | 1 | 1 |

---

## Quick Start — Local (Full Stack)

### Prerequisites

- Docker 24.0+ and Docker Compose 2.0+
- Git
- At minimum **12 GB RAM** allocated to Docker (Neo4j + Qdrant + AI models each consume 1–2 GB)

### Steps

**1. Clone the repository**

```bash
git clone https://github.com/Big-Data-Club/CoreApplication.git
cd CoreApplication
```

**2. Configure environment**

```bash
cp .env.example .env
```

Edit `.env` and fill in all `<TODO>` values. The critical ones for a first run are:

| Variable | Why it's required |
|----------|------------------|
| `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_USER` | Auth DB credentials |
| `LMS_POSTGRES_PASSWORD`, `LMS_POSTGRES_DB`, `LMS_POSTGRES_USER` | LMS DB credentials |
| `JWT_SECRET` | **Must be identical** in Auth and LMS services. Min 32 chars. |
| `LMS_API_SECRET` | Used by Auth to call LMS user-sync endpoint |
| `LMS_SYNC_SECRET` | **Must equal `LMS_API_SECRET`** |
| `REDIS_PASSWORD` | Redis auth |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Seeded on first boot |
| `GROQ_API_KEY` | Required for all AI generation features |
| `NEXTAUTH_SECRET` | NextAuth.js session signing. Min 32 chars. |
| `NEXTAUTH_URL` | e.g. `http://localhost:3000` |
| `STORAGE_TYPE` | Set to `minio` for AI document indexing to work |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | MinIO admin credentials |
| `NEO4J_PASSWORD` | Neo4j auth |

**3. Start the stack**

```bash
docker compose up -d --build
```

First boot takes 3–5 minutes. Wait for all services to become healthy:

```bash
docker compose ps
```

**4. Access the platform**

| Service | URL |
|---------|-----|
| Web App | http://localhost:3000 |
| Auth API / Swagger | http://localhost:3000/apiv1/swagger-ui.html |
| LMS API / Swagger | http://localhost:3000/lmsapidocs/swagger/index.html |
| AI API / Swagger | http://localhost:8000/docs |
| MinIO Console | http://localhost:9001 |
| Qdrant Dashboard | http://localhost:6333/dashboard |
| Neo4j Browser | http://localhost:7474/browser |

Log in with the `ADMIN_EMAIL` and `ADMIN_PASSWORD` you set in `.env`.

---

## Serverless Mode (Cloud DBs)

Use `docker-compose.serverless.yml` when running databases on managed cloud services instead of local Docker. In this mode, Postgres, Qdrant, Neo4j, and MinIO are **not** started as containers — instead the services point to external endpoints.

**Supported external services:**

| Service | Provider | Relevant env vars |
|---------|----------|------------------|
| Auth DB | Neon PostgreSQL | `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |
| LMS DB | Neon PostgreSQL | `LMS_POSTGRES_HOST`, ... |
| Lab DB | Neon PostgreSQL | `LAB_POSTGRES_HOST`, ... |
| Chat DB | Neon PostgreSQL | `CHAT_POSTGRES_HOST`, ... |
| AI DB | Neon PostgreSQL | `AI_POSTGRES_HOST`, ..., `AI_DB_SSL=require` |
| Vector DB | Qdrant Cloud | `QDRANT_URL`, `QDRANT_API_KEY` |
| Knowledge Graph | Neo4j Aura | `NEO4J_URI` (`bolt+s://...`), `NEO4J_USERNAME`, `NEO4J_PASSWORD` |
| Object Storage | Cloudflare R2 | `R2_ENDPOINT`, `MINIO_ROOT_USER` (Access Key ID), `MINIO_ROOT_PASSWORD` (Secret) |
| Lab Storage | Cloudflare R2 | `LAB_R2_ENDPOINT`, `LAB_MINIO_ROOT_USER`, `LAB_MINIO_ROOT_PASSWORD` |

**Start with serverless mode:**

```bash
docker compose -f docker-compose.serverless.yml up -d --build
```

---

## Environment Variables Reference

Full annotated list is in [`.env.example`](./.env.example). Below is a summary grouped by category.

### Shared Security Secrets — Must be consistent across services

```
JWT_SECRET          # Used by auth-service AND lms-service, lab-service, chat-service
LMS_API_SECRET      # auth-service → lms-service sync call auth header
LMS_SYNC_SECRET     # lms-service verifies incoming sync calls (must = LMS_API_SECRET)
CHAT_SYNC_SECRET    # auth-service → chat-service sync call auth header
AI_SERVICE_SECRET   # frontend/lms-service → ai-service internal auth
AI_KEY_ENCRYPTION_SECRET  # Encrypts stored LLM API keys per user
NEXTAUTH_SECRET     # NextAuth.js cookie signing
```

### AI Configuration

```
GROQ_API_KEY                      # Groq Cloud API key (required for LLM features)
AI_CHAT_MODEL=llama-3.1-8b-instant      # Chat/RAG model
AI_QUIZ_MODEL=llama-3.3-70b-versatile   # Quiz generation model (smarter, slower)
EMBEDDING_MODEL=BAAI/bge-m3             # ~1.2 GB download on first start
EMBEDDING_DIMENSIONS=1024
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
RERANK_FETCH_K=15                       # Candidates fetched before reranking
REINDEX_BATCH_SIZE=5                    # Docs processed per Kafka event (worker)
STORAGE_TYPE=minio                      # 'local' or 'minio' — minio required for AI
```

### Performance Tuning

```
HIKARI_MAX_POOL_SIZE=10     # Auth service DB connection pool
DB_MAX_OPEN_CONNS=50        # LMS / Lab service DB pool
DB_MAX_IDLE_CONNS=10
REDIS_POOL_SIZE=50          # LMS cache pool
GOMAXPROCS=2                # Go services — match to container CPU limit
```

### Cross-Origin (CORS)

Set `CORS_ALLOWED_ORIGINS` in your `.env` to your frontend domain(s):

```
CORS_ALLOWED_ORIGINS=https://bdc.hpcc.vn,http://localhost:3000,https://bdcweb.vercel.app
```

---

## API Documentation

All services generate interactive Swagger / OpenAPI docs automatically.

> **Recommendation:** Access API docs via the **frontend proxy paths** (port 3000) to avoid CORS issues with HTTP-only JWT cookies during local development.

### Auth Service — `/apiv1`
- Swagger UI (via proxy): [http://localhost:3000/apiv1/swagger-ui.html](http://localhost:3000/apiv1/swagger-ui.html)
- Direct: http://localhost:8080/swagger-ui.html
- Stack: Spring Boot 3 + Springdoc OpenAPI
- Handles: login, registration, role assignment, user sync, OAuth callbacks

### LMS Service — `/lmsapiv1`
- Swagger UI (via proxy): [http://localhost:3000/lmsapidocs/swagger/index.html](http://localhost:3000/lmsapidocs/swagger/index.html)
- Direct: http://localhost:8081/swagger/index.html
- Stack: Go + Swaggo
- Handles: courses, lessons, enrollments, quizzes, progress, file uploads, Kafka publish

### Lab Service — `/labapiv1`
- Direct: http://localhost:8082/swagger/index.html
- Stack: Go + Swaggo
- Handles: lab definitions, exercises, student submissions

### Chat Service — `/chatapiv1`
- Direct: http://localhost:8083/swagger/index.html (HTTP)
- WebSocket: `ws://localhost:8083/api/v1/ws` (or `wss://` in production)
- Stack: Go + Swaggo

### AI Service
- Swagger UI (via proxy): [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- Stack: FastAPI (auto-generated OpenAPI)
- Handles: semantic search, RAG Q&A, quiz generation, flashcards, knowledge graph queries

---

## Developer Notes

### Service Dependencies and Startup Order

```
kafka ─────────────────────────────────────────────────────────►
postgres ──────────────────────────────────────────────────────►
                  auth-service ────────────────────────────────►
postgres-lms ──────────────────────────────────────────────────►
                               lms-service ──────────────────►
postgres-lab ──────────────────────────────────────────────────►
                                            lab-service ──────►
redis ─────────────────────────────────────────────────────────►
                                                        chat-service ──►
postgres-ai + qdrant + neo4j + minio ──────────────────────────►
                                       ai-service ─────────────►
                                       ai-worker ──────────────►
                   (all services healthy) ──────────────────────►
                                                       frontend ──►
```

All inter-service calls are by **internal Docker DNS name** (e.g., `http://lms-backend:8081`). Never hardcode IPs.

### JWT is shared by ALL services

`JWT_SECRET` must be **identical** in Auth, LMS, Lab, and Chat services. Auth issues the JWT; LMS, Lab, and Chat validate it locally without calling Auth on every request.

### AI Model Cache

`ai-service` and `ai-worker` share the Docker volume `ai_model_cache:/app/.cache/models`. The model (`BAAI/bge-m3`, ~1.2 GB) downloads automatically on first boot. Subsequent restarts load from cache and are significantly faster.

### Kafka Topics (auto-created)

Kafka runs in **KRaft mode** (no ZooKeeper). Topics are auto-created with 3 partitions when first published to. Key topics:

| Topic | Producer | Consumer |
|-------|----------|---------|
| `document.uploaded` | lms-service | ai-worker |
| `video.added` | lms-service | ai-worker |
| `user.created` | auth-service | lms-service, chat-service (via API sync) |
| `course.event` | lms-service | personalize-service |

See [`docs/kafka-events.md`](./docs/kafka-events.md) for the full event schema.

### Viewing Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f ai-worker
docker compose logs -f lms-backend

# Last 100 lines
docker compose logs --tail=100 auth-service
```

---

## Contributing

Before making architectural changes, read:

- [`docs/TECHNICAL_NOTES.md`](file:///home/phucnhan/codespace/bdc/CoreApplication/docs/TECHNICAL_NOTES.md) — Critical gotchas: Kafka consumer group IDs, vector dimension constraints, Neo4j session management
- [`docs/DEVELOPER_GUIDE.md`](file:///home/phucnhan/codespace/bdc/CoreApplication/docs/DEVELOPER_GUIDE.md) — Local dev setup, branching strategy, coding standards
- [`docs/kafka-events.md`](file:///home/phucnhan/codespace/bdc/CoreApplication/docs/kafka-events.md) — Kafka topic schemas and consumer contracts
- [`docs/DEVOPS_SETUP.md`](file:///home/phucnhan/codespace/bdc/CoreApplication/docs/DEVOPS_SETUP.md) — Production deployment guide on a single VM using Docker Compose
- [`docs/DOCKER_TO_K8S_MIGRATION.md`](file:///home/phucnhan/codespace/bdc/CoreApplication/docs/DOCKER_TO_K8S_MIGRATION.md) — Step-by-step guide to migrate from Docker Compose to K3s Kubernetes
- [`docs/adr/`](file:///home/phucnhan/codespace/bdc/CoreApplication/docs/adr/) — Architecture Decision Records for all major design choices

### Branch naming

```
feature/your-feature-name
fix/bug-description
chore/task-description
```

### Commit convention (Conventional Commits)

```bash
git commit -m "feat(lms): add quiz retry limit per enrollment"
git commit -m "fix(ai-worker): handle empty PDF gracefully"
git commit -m "chore(docker): bump kafka to 3.8.0"
```

---

## License

This project is licensed under the [MIT License](./LICENSE).

---

Built by **BDC Team**