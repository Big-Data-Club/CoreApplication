-- =============================================================
-- USER CONCEPT MASTERY
-- Consolidated student mastery and struggle state per concept/node
-- =============================================================

CREATE TABLE IF NOT EXISTS user_concept_mastery (
    user_id           BIGINT NOT NULL,
    concept_id        BIGINT NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    mastery_level     DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    struggles         BOOLEAN NOT NULL DEFAULT FALSE,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    last_interaction  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, concept_id)
);

CREATE INDEX IF NOT EXISTS idx_ucm_user_concept ON user_concept_mastery(user_id, concept_id);
CREATE INDEX IF NOT EXISTS idx_ucm_concept ON user_concept_mastery(concept_id);
