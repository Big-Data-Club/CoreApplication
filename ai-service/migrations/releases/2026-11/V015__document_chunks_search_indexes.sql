-- ai-service/migrations/V015__document_chunks_search_indexes.sql
-- Accelerate lexical full-text search and trigram substring/exact matching for document_chunks.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Full-text search index using simple dictionary (matches to_tsvector('simple', chunk_text) in _keyword_search)
CREATE INDEX IF NOT EXISTS idx_dc_fts_simple
    ON document_chunks USING gin (to_tsvector('simple', chunk_text));

-- Trigram index for exact keyword matching, code tokens, numbers, and ILIKE queries
CREATE INDEX IF NOT EXISTS idx_dc_trgm
    ON document_chunks USING gin (chunk_text gin_trgm_ops);

ANALYZE document_chunks;
