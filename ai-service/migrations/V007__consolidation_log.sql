-- ── Graph consolidation audit log ─────────────────────────────────
-- Tracks every "Compact Graph" merge so teachers (and admins) can
-- audit which nodes were absorbed into which survivor and when.
--
-- One row per merge group. `absorbed_ids` holds every BIGINT node id
-- that was deleted; `old_names` is a JSONB mapping {id_str: name}
-- for human-readable history once the absorbed rows are gone.

CREATE TABLE IF NOT EXISTS graph_consolidation_log (
    id              BIGSERIAL PRIMARY KEY,
    course_id       BIGINT NOT NULL,
    survivor_id     BIGINT NOT NULL,
    absorbed_ids    BIGINT[] NOT NULL,
    old_names       JSONB,
    new_name        TEXT,
    new_description TEXT,
    chunks_moved    INTEGER DEFAULT 0,
    triggered_by    BIGINT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gcl_course   ON graph_consolidation_log(course_id);
CREATE INDEX IF NOT EXISTS idx_gcl_survivor ON graph_consolidation_log(survivor_id);
CREATE INDEX IF NOT EXISTS idx_gcl_created  ON graph_consolidation_log(created_at DESC);
