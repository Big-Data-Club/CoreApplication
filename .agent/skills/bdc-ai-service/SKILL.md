---
name: bdc-ai-service
description: >
  Use when working in ai-service/ — FastAPI HTTP server + aiokafka Worker.
  Covers: async document ingestion, error diagnosis, quiz generation,
  spaced repetition, knowledge graph, Qdrant, Neo4j, MinIO, pgvector fallback.
triggers:
  - ai-service/
  - fastapi
  - kafka
  - python
  - rag
  - embedding
  - qdrant
  - pgvector
  - quiz gen
  - diagnose
  - knowledge graph
  - neo4j
  - spaced repetition
  - flashcard
version: "2.1"
authors:
  - BDC Team
requires:
  - bdc-core-orchestrator
---

# BDC AI Service — Developer Skill

## Role & Scope

You are working on `ai-service/` — the AI/ML backend for the BDC LMS.
Built with Python 3.12 + FastAPI (HTTP) + aiokafka (async event worker).
Handles RAG document ingestion, error diagnosis, quiz generation, spaced
repetition scheduling, and knowledge graph management.

**Entry point (HTTP):** `main.py` -> FastAPI app
**Entry point (Worker):** `app/worker/kafka_worker.py` -> Kafka consumer loop
**Base URL:** `http://localhost:8000` | Docker: `http://ai-service:8000`
**Auth:** `X-AI-Secret: ${AI_SERVICE_SECRET}` on all endpoints

---

## Architecture

The service runs as **two separate processes** from the same Docker image:

| Process | Container | Command | Role |
|---------|-----------|---------|------|
| HTTP server | `ai-service` | `uvicorn main:app` | Sync queries, health, status reads |
| Kafka worker | `ai-worker` | `python -m app.worker.kafka_worker` | All heavy AI workloads |

**Rule:** Any operation taking > 2 s must run in `kafka_worker.py`, not in an
HTTP handler. HTTP handlers that trigger AI work publish a Kafka command and
return `202 Accepted` immediately.

---

## Project Structure

```
ai-service/
├── main.py                          FastAPI application factory
├── requirements.txt
├── migrations/
│   ├── 001_ai_core.sql              Core schema (tables, triggers, views)
│   ├── 002_schema_extensions.sql    Cache columns, content_index_status
│   └── 003_performance_indexes.sql  Covering indexes for hot paths
└── app/
    ├── api/
    │   └── endpoints/               FastAPI routers (health, diagnose, quiz, graph, SR)
    ├── core/
    │   ├── config.py                Pydantic settings (reads .env)
    │   ├── database.py              SQLAlchemy async engine (asyncpg)
    │   └── llm.py                   LLM + embedding model singletons
    ├── schemas/                     Pydantic request/response models
    ├── services/
    │   ├── rag_service.py           Embedding + Qdrant upsert/search (pgvector fallback)
    │   ├── diagnosis_service.py     RAG retrieval + LLM explanation
    │   ├── quiz_service.py          Bloom's taxonomy quiz generation
    │   ├── auto_index_service.py    Document chunking + node extraction pipeline
    │   ├── spaced_repetition_service.py  SM-2 scheduling
    │   ├── flashcard_service.py     Flashcard generation + repetition
    │   ├── qdrant_service.py        Qdrant collection management + client wrapper
    │   ├── neo4j_service.py         Neo4j driver wrapper + Cypher queries
    │   └── graph_linker.py          Cross-course knowledge link discovery
    └── worker/
        ├── kafka_worker.py          Main consumer loop (lms.ai.command, lms.document.uploaded)
        └── kafka_producer.py        publish_ai_job_status() + document status events
```

---

## Vector Storage

### Qdrant (default, `USE_QDRANT=true`)

Two collections, both 1024-dimensional cosine distance (bge-m3 model):

| Collection | Point ID | Payload stored |
|------------|----------|----------------|
| `document_chunks` | `document_chunks.id` (PG) | chunk_text, content_id, course_id, node_id, page_number |
| `knowledge_nodes` | `knowledge_nodes.id` (PG) | name, course_id, level, description |

gRPC port 6334 is used for batch upserts (`QDRANT_PREFER_GRPC=true`).
REST port 6333 is used for health checks.

### pgvector Fallback (`USE_QDRANT=false`)

Set `USE_QDRANT=false` to revert to the pgvector path without code changes.
The `embedding` column in `document_chunks` is nullable (not dropped) to
preserve rollback capability. See ADR-002.

---

## Knowledge Graph

### Neo4j (default, `NEO4J_ENABLED=true`)

Node label: `KnowledgeNode` with properties `{id, course_id, name, name_vi, level}`.
Edge types: `PREREQUISITE`, `EXTENDS`, `EQUIVALENT`, `RELATED`, `CONTRASTS_WITH`.
`cross_course=true` property marks edges discovered by `graph_linker.py`.

### PostgreSQL Fallback (`NEO4J_ENABLED=false`)

Graph endpoints fall back to `knowledge_node_relations` table queries.
Variable-depth traversal is limited to depth 3 via recursive CTE.

---

## Singleton Pattern — LLM and Embeddings

Models load exactly once per process via `app.core.llm`:

```python
# Always use these — never instantiate models directly in a service
from app.core.llm import get_llm, get_embedding_model

llm   = get_llm()             # ChatGroq (CHAT_MODEL or QUIZ_MODEL)
model = get_embedding_model() # SentenceTransformer (BAAI/bge-m3)
```

`ai-worker` runs with `USE_RERANKER=false` to save RAM. Only `ai-service`
(the HTTP server) loads the reranker. Do not add model loads outside these
singletons.

---

## Adding a New Kafka-Driven Feature

### Step 1 — Define the payload schema in `app/schemas/`

```python
# app/schemas/my_feature.py
from pydantic import BaseModel

class MyFeaturePayload(BaseModel):
    node_id: int
    course_id: int
    created_by: int
```

### Step 2 — Implement the service in `app/services/`

```python
# app/services/my_feature_service.py
from app.core.database import AsyncSessionLocal
from app.core.llm import get_llm

async def run_my_feature(node_id: int, course_id: int, created_by: int) -> dict:
    async with AsyncSessionLocal() as db:
        # fetch context, call LLM, write results
        llm = get_llm()
        ...
    return {"result": "..."}
```

### Step 3 — Register the command in `kafka_worker.py`

```python
# app/worker/kafka_worker.py  (inside process_ai_command)
async def process_ai_command(payload: dict):
    command_type = payload.get("command_type")
    job_id       = payload.get("job_id")

    try:
        if command_type == "MY_NEW_FEATURE":
            await publish_ai_job_status(job_id, "processing")
            result = await run_my_feature(
                node_id    = payload["node_id"],
                course_id  = payload["course_id"],
                created_by = payload["created_by"],
            )
            await publish_ai_job_status(job_id, "completed", result=result)

    except Exception as e:
        await publish_ai_job_status(job_id, "failed", error=str(e))
```

### Step 4 — Add the trigger endpoint in `app/api/endpoints/`

```python
# app/api/endpoints/my_feature.py
from fastapi import APIRouter, Depends
from app.worker.kafka_producer import publish_command
import uuid

router = APIRouter()

@router.post("/ai/my-feature", status_code=202)
async def trigger_my_feature(req: MyFeatureRequest, _=Depends(verify_ai_secret)):
    job_id = str(uuid.uuid4())
    await publish_command("MY_NEW_FEATURE", job_id, req.dict())
    return {"job_id": job_id, "status": "pending"}
```

### Step 5 — Register the router in `main.py`

```python
from app.api.endpoints.my_feature import router as my_feature_router
app.include_router(my_feature_router)
```

### Step 6 — Document the new command in `docs/kafka-events.md`

Add the payload schema under `lms.ai.command` -> command types and the result
shape under `ai.job.status` -> result shapes.

---

## Database Patterns

### Async Session

```python
from app.core.database import AsyncSessionLocal

async def my_service_fn():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DocumentChunk).where(DocumentChunk.course_id == course_id)
        )
        chunks = result.scalars().all()
```

### Raw asyncpg for performance-critical queries

```python
from app.core.database import get_db_connection

async def bulk_fetch():
    async with get_db_connection() as conn:
        rows = await conn.fetch(
            "SELECT id, chunk_text FROM document_chunks WHERE course_id = $1",
            course_id,
        )
```

---

## Error Handling Rules

1. The `consume_loop` in `kafka_worker.py` must never crash. Every command
   handler is wrapped in `try/except`. Failures publish `failed` status.

2. LLM rate limit errors (`groq.RateLimitError`) trigger exponential backoff
   (0.5 s, 1 s, 2 s, 4 s) before the job is marked failed.

3. Missing `job_id` in a Kafka message: log and discard. Do not publish status
   (there is no job to update).

4. HTTP endpoints return `500` with a generic message on unexpected errors.
   Never surface stack traces to the client.

---

## Environment Variables (AI-Specific)

| Variable | Default | Notes |
|----------|---------|-------|
| `USE_QDRANT` | `true` | `false` reverts to pgvector |
| `NEO4J_ENABLED` | `true` | `false` falls back to PostgreSQL graph queries |
| `USE_RERANKER` | `true` (ai-service) / `false` (ai-worker) | Reranker costs ~500 MB RAM |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | Change triggers cache invalidation (see TN-009) |
| `EMBEDDING_DIMENSIONS` | `1024` | Must match Qdrant collection dimensions |
| `GROQ_API_KEY` | — | Required. Get from console.groq.com |
| `CHAT_MODEL` | `llama-3.1-8b-instant` | Fast model for diagnosis |
| `QUIZ_MODEL` | `llama-3.3-70b-versatile` | Accurate model for quiz generation |
| `YOUTUBE_WHISPER_FALLBACK` | `false` | Enable only if captions are insufficient. Costs ~500 MB RAM. |
| `STORAGE_TYPE` | `minio` | Must be `minio` for AI worker to access files |
| `TOP_K_CHUNKS` | `3` | RAG retrieval top-k |
| `RERANK_FETCH_K` | `15` | Fetch this many chunks before reranking to top-k |

---

## Diagnosis Cache

Results are cached in Redis with TTL 24 h.
Cache key: `diagnosis:{question_id}:{md5(wrong_answer)}`.

After re-indexing a document, invalidate stale diagnoses:
```python
from app.core.cache import diagnosis_cache
await diagnosis_cache.invalidate_question(question_id)
```

No automated invalidation on re-index exists yet (TN-011).

---

## Embedding Cache

Cache key: `emb:{model_prefix}:{sha256(text)[:16]}`. TTL 7 days.

After an embedding model upgrade, flush all cached vectors:
```bash
docker exec redis-lms redis-cli -a "$REDIS_PASSWORD" KEYS "emb:*" | \
  xargs docker exec redis-lms redis-cli -a "$REDIS_PASSWORD" DEL
```

---

## Code Quality Checklist

Before submitting any change to this service:

```
[ ] New Kafka command registered in kafka_worker.py with try/except
[ ] New command publishes "processing" status before starting work
[ ] New command publishes "completed" or "failed" in all code paths
[ ] New service function uses get_llm() / get_embedding_model() singletons
[ ] All DB access uses AsyncSessionLocal (no synchronous DB calls in event loop)
[ ] New endpoint has X-AI-Secret verification dependency
[ ] New command documented in docs/kafka-events.md
[ ] No model instantiation outside app/core/llm.py
[ ] No raw os.environ[] — use app/core/config.py settings object
[ ] Tests added: at least endpoint auth test + worker command test
```