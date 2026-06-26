---
name: bdc-core-orchestrator
description: >
  ALWAYS load this before any other BDC skill.
  Covers: full microservices architecture, environment variables, secrets,
  CORS, Docker Compose, CI/CD, Kafka event bus, and inter-service API contracts.
triggers:
  - architecture
  - docker
  - compose
  - env
  - global
  - cors
  - secrets
  - kafka
version: "2.1"
authors:
  - BDC Team
---

# BDC Core Orchestrator - Global Architecture

**Read this file completely before working on any individual service.**
You are modifying the **Big Data Club (BDC) Core Application** - a production
microservices LMS deployed via Docker Compose on a single server.

---

## The Three Golden Rules

1. **Never mock Auth in LMS.** The LMS uses `UserSyncService` to replicate
   user records from Auth into its own PostgreSQL instance. Cross-service joins
   do not exist. If users are missing from the LMS DB, re-run the sync API.

2. **Never use synchronous HTTP for AI tasks.** All AI workloads exceeding ~2 s
   must be executed via Kafka. The HTTP endpoint returns `202 Accepted` + `job_id`
   immediately. The client polls the Redis status cache.

3. **Never hardcode credentials or hostnames.** All service URLs use Docker
   internal hostnames (e.g. `http://lms-backend:8081`). All secrets come from
   `.env`. Never commit `.env`.

---

## System Topology

```
+------------------+       +------------------+
|  Next.js 14      |       |  Traefik         |
|  frontend/       +------>+  (prod reverse   |
|  :3000           |       |   proxy)         |
+--------+---------+       +------------------+
         |
         | /apiv1/*        -> http://backend:8080
         | /lmsapiv1/*     -> http://lms-backend:8081
         | /files/*        -> http://lms-backend:8081 (file serving)
         |
+--------v---------+       +------------------+       +------------------+
|  auth-and-       |  HTTP |  lms-service/    | Kafka |  ai-service/     |
|  management-     +------>+  Go 1.24 + Gin   +------>+  FastAPI +       |
|  service/        | sync  |  :8081           |       |  ai-worker       |
|  Spring Boot 3.x |       |                  |<------+  :8000           |
|  Java 21  :8080  |       +--+-------+-------+       +--------+---------+
+--------+---------+          |       |                        |
         |                    |       |                        |
+--------v---------+  +-------v--+ +--v------+  +------------v---------+
| PostgreSQL       |  | PostgreSQL| | Redis   |  | PostgreSQL  Qdrant   |
| (auth DB)  :5433 |  | (lms DB)  | | :6379   |  | (ai DB)     Neo4j    |
+------------------+  | :5434     | +---------+  | :5435       :7687    |
                       +-----------+              +----------------------+
                                   |
                       +-----------v-----------+
                       | MinIO object storage  |
                       | :9000 (API) :9001 (UI)|
                       +-----------------------+
```

---

## Service Reference

| Service | Directory | Stack | Internal hostname | Port |
|---------|-----------|-------|-------------------|------|
| Frontend | `frontend/` | Next.js 14, TypeScript | `frontend` | 3000 |
| Auth | `auth-and-management-service/` | Java 21, Spring Boot 3.x | `backend` | 8080 |
| LMS | `lms-service/` | Go 1.24, Gin | `lms-backend` | 8081 |
| AI HTTP | `ai-service/` | Python 3.12, FastAPI | `ai-service` | 8000 |
| AI Worker | `ai-service/` | Python 3.12, aiokafka | `ai-worker` | - |
| Kafka | - | KRaft mode | `kafka` | 9092 |
| Auth DB | - | PostgreSQL 15 | `postgres` | 5433->5432 |
| LMS DB | - | PostgreSQL 15 | `postgres-lms` | 5434->5432 |
| AI DB | - | PostgreSQL 15 | `postgres-ai` | 5435->5432 |
| Redis | - | Redis 7 | `redis-lms` | 6379 |
| MinIO | - | MinIO latest | `minio` | 9000/9001 |
| Qdrant | - | Qdrant v1.13.6 | `qdrant` | 6333/6334 |
| Neo4j | - | Neo4j 5.x | `neo4j` | 7687 |

---

## Database Ownership

Each service owns its database exclusively. Cross-service data access uses APIs,
not direct DB connections.

| Database | Owner | Tables (summary) |
|----------|-------|-----------------|
| `postgres` (auth) | auth-service | `users`, `events`, `tasks`, `announcements`, `password_reset_tokens` |
| `postgres-lms` (lms) | lms-service | `users`*, `courses`, `sections`, `content`, `enrollments`, `quizzes`, `quiz_attempts`, `forum_posts` |
| `postgres-ai` (ai) | ai-service + ai-worker | `knowledge_nodes`, `document_chunks`, `ai_diagnoses`, `spaced_repetitions`, `flashcards`, `content_index_status` |

*LMS `users` table is populated exclusively via the user sync API, not direct writes.

---

## AI Database Migrations

Migration files live in `ai-service/migrations/` and are mounted as Docker
initdb scripts (run only on empty volume). All files are idempotent.

| File | Purpose |
|------|---------|
| `001_ai_core.sql` | Core schema: knowledge_nodes, document_chunks, ai_diagnoses, spaced_repetitions, flashcards, ai_quiz_generations |
| `002_schema_extensions.sql` | Cache columns on ai_diagnoses, content_index_status table, source_content_title on knowledge_nodes |
| `003_performance_indexes.sql` | Covering indexes for hot query paths |

**To apply to an existing deployment:**
```bash
docker exec -i postgres-ai psql -U "$AI_POSTGRES_USER" -d "$AI_POSTGRES_DB" \
  < ai-service/migrations/002_schema_extensions.sql
```

---

## Cross-Service Communication Patterns

### Pattern 1 - User Sync (Auth -> LMS)

Triggered when users are created, updated, or blocked in the Auth service.

```
auth-service
    |
    | POST http://lms-backend:8081/api/v1/sync/users
    | Header: X-Sync-Secret: ${LMS_SYNC_SECRET}
    | Body:   [{user_id, email, full_name, roles}]
    |
    v
lms-service  ->  INSERT/UPDATE users table
```

`UserSyncService.syncUsersToLms()` is `@Async`. Failures are logged but do not
fail the HTTP response. Monitor with:
```bash
docker compose logs backend | grep -i "sync\|error"
```

### Pattern 2 - Event-Driven AI (LMS -> Kafka -> AI Worker -> Redis -> LMS)

Used for all AI tasks: document ingestion, quiz generation, flashcards, diagnosis.

```
1. Client   -> POST /lmsapiv1/ai/quiz   (LMS endpoint)
2. LMS      -> Kafka topic: lms.ai.command   {job_id, command_type, payload}
3. LMS      -> Redis SET ai_job:{job_id} = {status: "pending"}
4. LMS      -> HTTP 202 {job_id}
5. ai-worker -> Kafka POLL lms.ai.command
6. ai-worker -> Kafka PUB ai.job.status  {job_id, status: "processing"}
7. ai-worker -> executes LLM / embedding / DB writes
8. ai-worker -> Kafka PUB ai.job.status  {job_id, status: "completed", result: {...}}
9. lms-service -> Kafka POLL ai.job.status -> Redis SET ai_job:{job_id}
10. Client  -> GET /lmsapiv1/ai/jobs/{job_id}/status -> reads Redis
```

### Pattern 3 - Synchronous AI (LMS -> AI HTTP)

Used only for fast, non-LLM queries (health, status reads, graph GET).

```
lms-service  ->  GET http://ai-service:8000/ai/process-document/{id}
               Header: X-AI-Secret: ${AI_SERVICE_SECRET}
```

### Pattern 4 - File Access (LMS ↔ MinIO, AI ← MinIO)

```
Client  ->  POST /lmsapiv1/files/upload
lms-service  ->  MinIO PUT s3://lms-files/{key}
ai-worker    ->  MinIO GET s3://lms-files/{key}   (direct SDK, not HTTP)
Client  ->  GET /files/{key}  (proxied to lms-service file serve endpoint)
```

---

## Critical Environment Variables

Variables marked `[MUST MATCH]` must be identical in both services.

| Variable | Services | Notes |
|----------|----------|-------|
| `JWT_SECRET` | backend, lms-backend | **[MUST MATCH]** Min 32 chars. Silent 401 if they differ. |
| `LMS_API_SECRET` | backend | Sent as `X-Sync-Secret` header |
| `LMS_SYNC_SECRET` | lms-backend | **[MUST MATCH `LMS_API_SECRET`]** |
| `AI_SERVICE_SECRET` | lms-backend, ai-service, ai-worker | Internal auth for AI HTTP calls |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | lms-backend, ai-service, ai-worker | Same credentials for all |
| `REDIS_PASSWORD` | lms-backend, ai-service, ai-worker | All use same Redis instance |

---

## Docker Compose Operations

```bash
# Start full stack (first time - builds images)
docker compose up -d --build

# Start without rebuilding
docker compose up -d

# Rebuild a single service after code change
docker compose up -d --build ai-worker

# Check all service health
docker compose ps

# Stream logs
docker compose logs -f ai-worker
docker compose logs -f lms-backend

# Stop - preserve data volumes
docker compose down

# Stop - destroy data volumes (⚠ deletes all data)
docker compose down -v
```

---

## Kafka Topics Reference

| Topic | Producer | Consumer | Retention |
|-------|----------|----------|-----------|
| `lms.document.uploaded` | lms-service | ai-worker | 7 days |
| `lms.ai.command` | lms-service | ai-worker | 7 days |
| `lms.graph.command` | lms-service | ai-worker | 7 days |
| `lms.maintenance.command` | lms-service / admin | ai-worker | 7 days |
| `ai.document.processed.status` | ai-worker | lms-service | 1 day |
| `ai.job.status` | ai-worker | lms-service | 1 day |
| `ai.graph.status` | ai-worker | lms-service | 1 day |

Consumer group IDs: `ai-worker-group` (ai-worker), `lms-ai-status-group` (lms-service).
These must never overlap - see TN-008.

---

## CI/CD Overview

- **CI** (`ci.yml`): triggered on PR and push. Detects changed services, runs
  tests in parallel (`./mvnw test`, `go test ./...`, `pytest`), scans images
  with Trivy, pushes to Docker Hub on merge to `main` or `develop`.

- **CD** (`cd-production.yml`): triggered on merge to `main`. SSHs into the
  production server and runs `docker compose pull && docker compose up -d`.

Required GitHub secrets: `DOCKER_USERNAME`, `DOCKER_PASSWORD`, `SSH_HOST`,
`SSH_USER`, `SSH_PRIVATE_KEY`.