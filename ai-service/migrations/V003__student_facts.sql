-- ── student_facts ───────────────────────────────────────────────
-- Stores long-term facts (weaknesses, preferences, goals, notes) about students.
-- Forms the metadata foundation for the LTM (Long-Term Memory) system.
CREATE TABLE IF NOT EXISTS student_facts (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    fact        TEXT NOT NULL,
    category    VARCHAR(50) NOT NULL,  -- weakness, preference, goal, personal, note
    course_id   BIGINT,                -- NULL = cross-course
    qdrant_point_id BIGINT,            -- NULL if Qdrant write failed (sync later)
    qdrant_synced BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sf_user ON student_facts(user_id);
CREATE INDEX IF NOT EXISTS idx_sf_user_cat ON student_facts(user_id, category);
CREATE INDEX IF NOT EXISTS idx_sf_unsynced ON student_facts(qdrant_synced) WHERE NOT qdrant_synced;
