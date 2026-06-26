# ADR-002: Qdrant as Primary Vector Store (replacing pgvector)

| Field    | Value                          |
|----------|--------------------------------|
| Status   | Accepted                       |
| Date     | 2025-01-01                     |
| Authors  | BDC Team                       |

## Context

The RAG pipeline stores dense vector embeddings (1024-dimensional, bge-m3 model)
for two collections: `document_chunks` and `knowledge_nodes`.

The initial implementation stored embeddings in PostgreSQL using the `pgvector`
extension (a `VECTOR(1024)` column with an HNSW index). As the document corpus
grew, two problems emerged:

1. **Memory pressure:** The HNSW graph for `document_chunks` occupies approximately
   400 MB of shared_buffers per 100,000 chunks. PostgreSQL competes with the
   application connection pool for this memory.

2. **Query latency:** ANN search via pgvector requires a `<=>` cosine distance
   operator in the query planner. With filter conditions (`WHERE course_id = $1`),
   PostgreSQL sometimes chooses a sequential scan over the HNSW index, causing
   p99 latencies above 500ms on large corpora.

## Decision

Qdrant is used as the primary vector store for both collections.
PostgreSQL (AI DB) retains all non-vector metadata (chunk text, node names,
relationships, job statuses).

The migration is controlled by a feature flag: `USE_QDRANT=true` (default).
Setting `USE_QDRANT=false` reverts to the pgvector path without code changes.

## Rationale

### Alternative A: Tune pgvector
- Increase `maintenance_work_mem` for index builds; increase `shared_buffers`
- Pros: No additional infrastructure; single database
- Cons: Requires PostgreSQL tuning expertise; memory competition persists;
  filter + ANN combination remains suboptimal; does not address latency at scale
- Reason rejected: Addressable short-term but not scalable beyond ~500k chunks

### Alternative B: Weaviate
- Pros: Built-in multi-tenancy matching our course_id partitioning pattern
- Cons: Heavier resource footprint; Java-based (different runtime than the stack);
  less mature Python async client at the time of evaluation
- Reason rejected: Resource overhead too high for current server capacity

### Chosen: Qdrant
- Written in Rust; very low memory overhead for HNSW graph (~4 bytes/vector/link)
- gRPC transport significantly faster than REST for batch upserts
- Native payload filtering runs before ANN (pre-filtering), eliminating the
  sequential scan problem with pgvector
- `on_disk=true` for vector storage keeps HNSW graph in RAM while cold
  vector data lives on SSD - good balance for our access pattern
- Python async client (`qdrant-client[async]`) with full type annotations

## Implementation

Two collections created at startup (`init_collections()`):

```
document_chunks:   1024d, cosine, HNSW m=16 ef_construct=128, on_disk=true
knowledge_nodes:   1024d, cosine, HNSW m=16 ef_construct=128, on_disk=true
```

Point IDs map 1:1 to PostgreSQL row IDs, eliminating any ID translation layer.
Full payload stored in each Qdrant point so search results require no secondary
database round-trip on the hot query path.

## Rollback Plan

Set `USE_QDRANT=false` in environment. All search and upsert paths in
`rag_service.py` and `auto_index_service.py` have explicit pgvector fallback
branches. The pgvector `embedding` column in `document_chunks` is nullable
(not dropped) to support this rollback.

To re-enable pgvector path after a rollback, run:
```bash
python scripts/migrate_ai_data.py --tables document_chunks knowledge_nodes
```
This re-populates the `embedding` column from the Qdrant backup copy.

## Consequences

### Positive
- Sub-100ms p99 for ANN search with payload filter on 500k+ chunks
- Memory footprint of PostgreSQL reduced by ~400 MB
- Batch upsert throughput ~10x faster via gRPC vs pgvector SQL batch

### Negative
- Additional service dependency (Qdrant container)
- Two systems must be kept in sync (PG metadata + Qdrant vectors)
- Qdrant downtime makes semantic search unavailable (not just degraded)

### Risks
- Risk: Qdrant data loss causes inconsistency with PostgreSQL metadata.
  Mitigation: `migrate_to_qdrant.py` re-populates Qdrant from PG if vectors exist;
  `auto_index` with `force=true` re-ingests documents from scratch.

## References
- `ai-service/app/services/qdrant_service.py` - client wrapper
- `ai-service/app/services/rag_service.py` - routing logic (use_qdrant flag)
- `ai-service/scripts/migrate_to_qdrant.py` - migration script
- `docker-compose.yml` - Qdrant service configuration
