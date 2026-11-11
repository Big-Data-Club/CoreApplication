-- Agent-built course knowledge maps. Rows created by the MCP knowledge-map
-- tools carry a stable external key so a retry updates the same concept
-- instead of duplicating it. Human and auto-indexed rows keep NULL keys and
-- are never overwritten by the agent.
ALTER TABLE knowledge_nodes
    ADD COLUMN IF NOT EXISTS managed_by VARCHAR(32),
    ADD COLUMN IF NOT EXISTS external_key VARCHAR(160),
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE UNIQUE INDEX IF NOT EXISTS uq_kn_course_external_key
    ON knowledge_nodes (course_id, external_key)
    WHERE external_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_kn_course_managed
    ON knowledge_nodes (course_id, managed_by)
    WHERE managed_by IS NOT NULL;
