# Technical Notes

| Field     | Value                     |
|-----------|---------------------------|
| Version   | 2.1.0                     |
| Status    | Approved                  |
| Date      | 2026-04-19                |
| Authors   | BDC Team                  |
| Reviewers | —                         |

## Revision History

| Version | Date       | Author   | Description                              |
|---------|------------|----------|------------------------------------------|
| 1.0.0   | 2025-01-01 | BDC Team | Initial draft                            |
| 2.0.0   | 2025-01-01 | BDC Team | Adds Qdrant, Neo4j, Kafka, Phase 2 notes |
| 2.1.0   | 2026-04-19 | BDC Team | Documentation standardization            |

Read this before making changes to authentication, AI pipeline, or Docker setup.

---

## Section 1: Authentication & JWT

### TN-001: JWT_SECRET must be identical in auth-service and lms-service

**Context:** Both services verify JWT tokens independently. They do not call
each other to validate. `JWT_SECRET` in `.env` is consumed by both.

**Detail:** If the secrets differ, lms-service rejects every token issued by
auth-service with `401 Unauthorized`. No log message explains the mismatch.

**Impact:** All authenticated LMS requests fail silently.

**Fix:** Single `JWT_SECRET` value in `.env`, minimum 32 characters.
Verify: `grep JWT_SECRET .env | wc -c` — output should be the same for both
service containers.

---

### TN-002: DataInitializer reads admin credentials from environment

**Context:** `DataInitializer.java` seeds the admin account on first startup.

**Detail:** Admin email and password are read from `${ADMIN_EMAIL}` and
`${ADMIN_PASSWORD}`. If these are not set, Spring Boot fails at startup with
a `@Value` injection error.

**Fix:** Set both in `.env` before first run. Change the password on first login.

---

## Section 2: User Sync

### TN-003: User sync is async — silent failure on LMS downtime

**Context:** `UserSyncService.syncUsersToLms()` is `@Async`. It fires after
`bulkRegister()` completes and does not block the HTTP response.

**Detail:** If lms-service is down at creation time, the sync silently fails.
Users exist in the auth DB but cannot access LMS features because their
record is absent from the LMS `users` table.

**Impact:** Newly created users receive "user not found" on LMS endpoints.

**Fix:** Manual re-sync after verifying lms-service is healthy:
```bash
curl -X POST http://localhost:8081/api/v1/sync/users/bulk \
  -H "X-Sync-Secret: $LMS_SYNC_SECRET" \
  -H "Content-Type: application/json" \
  -d '[{"user_id":1,"email":"a@b.com","full_name":"Name","roles":["TEACHER","STUDENT"]}]'
```

Monitor for sync failures:
```bash
docker compose logs backend | grep -i "sync\|error"
```

---

### TN-004: LMS_API_SECRET and LMS_SYNC_SECRET must be equal

**Context:** auth-service sends the sync header `X-Sync-Secret: ${LMS_API_SECRET}`.
lms-service validates incoming requests against `${LMS_SYNC_SECRET}`.

**Detail:** Two different variable names, same secret. If they differ, every
sync request returns `401` and user access to LMS breaks (see TN-003 impact).

**Fix:** Set `LMS_API_SECRET` and `LMS_SYNC_SECRET` to the same value in `.env`.

---

## Section 3: File Storage

### TN-005: STORAGE_TYPE must be `minio` for AI document processing

**Detail:** lms-service reads `STORAGE_TYPE` from environment.
- `local` — stores files in the container filesystem at `/app/uploads`.
- `minio` — stores files in the MinIO bucket `lms-files`.

The AI worker (`ai-worker`) fetches files directly from MinIO via SDK.
It does not read from the local filesystem.

**Impact:** If `STORAGE_TYPE=local`, the AI worker cannot access uploaded
documents. Auto-index jobs fail silently.

**Fix:** Use `STORAGE_TYPE=minio` in any environment where ai-worker processes
documents. `local` is only suitable for frontend-only development.

---

## Section 4: AI Database Migrations

### TN-006: Two conflicting 002_*.sql files (fixed in 002_schema_extensions.sql)

**Context:** The original repo contained `002_add_diagnosis_cache_fields.sql`
and `002_decouple_lms.sql` — two files with the same numeric prefix. The
`docker-compose.yml` only mounted `001_ai_core.sql` and
`003_performance_indexes.sql`, so both `002_*` files were never applied on
fresh installs.

**Detail:** Missing migrations caused:
- `content_index_status` table absent -> auto-index status tracking broken.
- `ai_diagnoses.knowledge_gap`, `.study_suggestion`, `.suggested_docs_json`
  columns absent -> diagnosis cache queries failed with column-not-found errors.
- `knowledge_nodes.source_content_title` absent -> knowledge graph title map
  queries failed.

**Fix:** Both files are consolidated into `002_schema_extensions.sql`. The
`docker-compose.yml` `postgres-ai` service now mounts all three files.

**To apply on an existing deployment:**
```bash
docker exec -i postgres-ai psql -U "$AI_POSTGRES_USER" -d "$AI_POSTGRES_DB" \
  < ai-service/migrations/002_schema_extensions.sql
```

---

## Section 5: Vector Storage (Qdrant)

### TN-007: USE_QDRANT=false to roll back to pgvector

**Context:** Qdrant is the default vector backend (see ADR-002).

**Detail:** Set `USE_QDRANT=false` in ai-service and ai-worker environments to
revert all vector operations to pgvector. The `embedding` column in
`document_chunks` is nullable and preserved for this purpose.

**Impact:** Semantic search degrades on corpora > 100k chunks. p99 latency
may exceed 500 ms with filter + ANN combined queries.

---

### TN-008: Qdrant collection dimensions must match EMBEDDING_DIMENSIONS

**Detail:** Collections `document_chunks` and `knowledge_nodes` are created
with `vector_size=1024` (bge-m3 default). If `EMBEDDING_MODEL` is changed
to a model with different output dimensions, the Qdrant collections must be
recreated or the upsert will fail with a dimension mismatch error.

**Fix:** After an embedding model change:
1. Delete existing Qdrant collections via REST: `DELETE http://localhost:6333/collections/document_chunks`
2. Update `EMBEDDING_DIMENSIONS` in `.env`.
3. Re-trigger auto-index for all content: `POST /ai/auto-index?force=true`

---

## Section 6: Knowledge Graph (Neo4j)

### TN-009: NEO4J_ENABLED=false to run without knowledge graph

**Detail:** Set `NEO4J_ENABLED=false` to disable all Neo4j operations.
Graph endpoints (`GET /ai/knowledge-graph/*`) fall back to PostgreSQL queries.
Cross-course prerequisite discovery is unavailable in fallback mode.

---

## Section 7: Kafka

### TN-010: Kafka consumer group IDs must not overlap

**Context:** `ai-service` (HTTP server) and `ai-worker` (Kafka consumer)
are separate processes that share the same Docker image.

**Detail:** The ai-worker uses `group_id="ai-worker-group"`. If any other
process joins this group, Kafka rebalances partitions between them. Document
indexing and AI command events may be consumed by the HTTP server process,
which does not handle them.

**Impact:** Kafka events are silently discarded.

**Fix:** Never set `group_id="ai-worker-group"` in any process other than
`ai-worker`.

---

### TN-011: Checking Kafka consumer lag

```bash
docker exec bdc-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group ai-worker-group
```

LAG column thresholds:
- `0` or near-zero: healthy.
- `> 100`: worker falling behind — check worker logs.
- `> 500`: critical — scale the worker or investigate errors.

HTTP alternative (Phase 3 feature):
```bash
curl http://localhost:8000/health/kafka
```

---

## Section 8: AI Caching

### TN-012: Diagnosis cache invalidation after content re-index

**Context:** LLM diagnosis results are cached in Redis with TTL 24 h.
Cache key: `diagnosis:{question_id}:{md5(wrong_answer)}`.

**Detail:** If a course document is re-indexed with corrected content,
cached diagnoses for affected questions remain stale for up to 24 h.
No automated invalidation on re-index exists yet.

**Fix:** After a forced re-index, invalidate manually:
```python
from app.core.cache import diagnosis_cache
await diagnosis_cache.invalidate_question(question_id)
```

---

### TN-013: Embedding cache TTL is 7 days

**Context:** Computed embeddings are cached in Redis.
Cache key: `emb:{model_prefix}:{sha256(text)[:16]}`.

**Detail:** After an embedding model upgrade, cached vectors from the old
model continue to be served for up to 7 days, producing incorrect search
results.

**Fix:** Flush the embedding cache after any model upgrade:
```bash
docker exec redis-lms redis-cli -a "$REDIS_PASSWORD" KEYS "emb:*" | \
  xargs docker exec redis-lms redis-cli -a "$REDIS_PASSWORD" DEL
```

---

### TN-014: YOUTUBE_WHISPER_FALLBACK=true costs ~500 MB RAM per worker

**Context:** If a YouTube video has no captions, the worker downloads the
audio and runs Whisper locally.

**Detail:** `faster-whisper` (base model) loads ~500 MB into RAM. With the
ai-worker memory limit at 2 GB, this reduces headroom for embeddings and
LLM calls.

**Default:** `YOUTUBE_WHISPER_FALLBACK=false`. Enable only when YouTube
caption availability is insufficient.

---

## Section 9: Known Test Failures

### TN-015: AuthServiceTest.testBulkRegister_AssignsDefaultPassword is incorrect

**Status:** Not fixed — known issue.

**Fix:** Update the test assertion to match the actual generated password
logic in `PasswordGenerator.java`.

---

### TN-016: EventControllerTest.testUpdateEvent_Success asserts wrong enum

**Detail:** The test asserts `.status = "ONGOING"` but the enum value is `"IN_PROGRESS"`.

**Fix:**
```java
.andExpect(jsonPath("$.status").value("IN_PROGRESS"))
```

---

## Section 10: Operations

### TN-017: Applying migrations to an existing deployment

initdb scripts only run when the PostgreSQL data volume is empty. For existing
deployments, apply manually:

```bash
# AI DB — apply 002 extension migration (if not yet applied)
docker exec -i postgres-ai psql -U "$AI_POSTGRES_USER" -d "$AI_POSTGRES_DB" \
  < ai-service/migrations/002_schema_extensions.sql

# AI DB — apply performance indexes (idempotent, safe to re-run)
docker exec -i postgres-ai psql -U "$AI_POSTGRES_USER" -d "$AI_POSTGRES_DB" \
  < ai-service/migrations/003_performance_indexes.sql

# Verify content_index_status table exists
docker exec postgres-ai psql -U "$AI_POSTGRES_USER" -d "$AI_POSTGRES_DB" \
  -c "\dt content_index_status"

# Verify diagnosis cache columns
docker exec postgres-ai psql -U "$AI_POSTGRES_USER" -d "$AI_POSTGRES_DB" \
  -c "\d ai_diagnoses" | grep knowledge_gap
```

---

### TN-018: Migrating vectors from pgvector to Qdrant (one-time)

```bash
docker exec ai-worker python scripts/migrate_to_qdrant.py
```

---

### TN-019: Migrating knowledge graph from PostgreSQL to Neo4j (one-time)

```bash
docker exec ai-worker python scripts/migrate_neo4j.py
```

---

### TN-020: Re-syncing all users from auth-service to lms-service

```bash
curl -X POST http://localhost:8081/api/v1/sync/users/bulk \
  -H "X-Sync-Secret: $LMS_SYNC_SECRET" \
  -H "Content-Type: application/json" \
  -d @<(docker exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -tAc "SELECT json_agg(json_build_object(
      'user_id',id,'email',email,'full_name',full_name,
      'roles',ARRAY['TEACHER','STUDENT']
    )) FROM users")
```

---

## Section 11: Production Checklist

```
[ ] JWT_SECRET min 32 chars, identical in backend and lms-backend containers
[ ] LMS_API_SECRET equals LMS_SYNC_SECRET
[ ] AI_SERVICE_SECRET set and consistent across lms-backend, ai-service, ai-worker
[ ] ADMIN_EMAIL and ADMIN_PASSWORD set (DataInitializer reads these)
[ ] ADMIN_PASSWORD changed on first login
[ ] STORAGE_TYPE=minio in any environment using ai-worker
[ ] GlobalExceptionHandler.java: stack trace hidden in docker/prod profiles
[ ] JwtAuthFilter.java: System.out.println statements removed
[ ] CorsConfig.java: allowedOrigins read from env var, not hardcoded
[ ] NEO4J_PASSWORD changed from default
[ ] All [REQUIRED] variables in .env.example filled in .env
[ ] 002_schema_extensions.sql applied to postgres-ai (if upgrading from old install)
```