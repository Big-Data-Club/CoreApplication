-- ai-service/migrations/004_graphrag_indexes.sql
--
-- GraphRAG performance indexes and materialized view.
-- These are ADDITIVE only - no tables or columns are dropped.
-- Safe to run on existing deployments.
--
-- Apply to running system:
--   docker exec -i postgres-ai psql -U "$AI_POSTGRES_USER" -d "$AI_POSTGRES_DB" \
--     < ai-service/migrations/004_graphrag_indexes.sql

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Composite index: fast lookup of ready chunks by node_id
--    Used by graphrag_service.retrieve() graph-expansion phase.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_node_status
  ON document_chunks (node_id, status)
  WHERE status = 'ready' AND node_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Covering index: node_id lookup that covers all graphrag read columns
--    Avoids heap-page fetches for the search_by_node_ids hot path.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_node_covering
  ON document_chunks (node_id, id, content_id, course_id, chunk_level)
  WHERE status = 'ready' AND node_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Partial index on chunk_level for child-only keyword search
--    Speeds up the existing _keyword_search query which already filters
--    chunk_level = 'child'.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_child_level
  ON document_chunks (course_id, id)
  WHERE status = 'ready' AND chunk_level = 'child';

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Materialized view: concept_chunk_map
--    Provides a fast per-node chunk count. Refreshed by the AI worker
--    after each indexing job via REFRESH MATERIALIZED VIEW CONCURRENTLY.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS concept_chunk_map AS
SELECT
  node_id,
  course_id,
  COUNT(*)                   AS chunk_count,
  MAX(created_at)            AS last_indexed,
  MIN(created_at)            AS first_indexed
FROM document_chunks
WHERE status = 'ready'
  AND node_id IS NOT NULL
GROUP BY node_id, course_id
WITH DATA;

-- Unique index so we can refresh concurrently
CREATE UNIQUE INDEX IF NOT EXISTS idx_ccm_node_course
  ON concept_chunk_map (node_id, course_id);

-- Fast lookup by course_id alone
CREATE INDEX IF NOT EXISTS idx_ccm_course
  ON concept_chunk_map (course_id);
