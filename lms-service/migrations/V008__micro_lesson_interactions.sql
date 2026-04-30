-- ── MICRO-LESSON INTERACTIONS ────────────────────────────────────
-- Raw analytics log produced by the Quick Action Panel sitting at
-- the bottom of the MicroLessonViewer. Every flashcard flip, quick
-- check answer, "Ask AI" message and lesson completion is appended
-- here synchronously, then a Kafka event is fan-out asynchronously
-- to the analytics worker that maintains node-level mastery scores.

CREATE TABLE IF NOT EXISTS micro_lesson_interactions (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id       BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    lesson_id       BIGINT REFERENCES micro_lessons(id) ON DELETE SET NULL,
    node_id         BIGINT,
    action_type     VARCHAR(40) NOT NULL
                       CHECK (action_type IN (
                            'lesson_view',
                            'lesson_complete',
                            'flashcard_flip',
                            'flashcard_rate',
                            'quick_check_attempt',
                            'quick_check_correct',
                            'quick_check_incorrect',
                            'ask_ai'
                       )),
    score           DOUBLE PRECISION,
    status          VARCHAR(40),
    payload         JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mli_user_course   ON micro_lesson_interactions(user_id, course_id);
CREATE INDEX IF NOT EXISTS idx_mli_node          ON micro_lesson_interactions(node_id);
CREATE INDEX IF NOT EXISTS idx_mli_lesson        ON micro_lesson_interactions(lesson_id);
CREATE INDEX IF NOT EXISTS idx_mli_action        ON micro_lesson_interactions(action_type);
CREATE INDEX IF NOT EXISTS idx_mli_created_at    ON micro_lesson_interactions(created_at DESC);


-- ── KNOWLEDGE NODE MASTERY (composite, weighted) ────────────────
-- Maintained by the analytics worker that consumes
-- `lms.analytics.interactions`. The heatmap endpoint reads from this
-- materialised table directly so the API response is O(1) per node.
--
-- Mastery weights (sum to 1.0):
--   * formal_quiz_score      → 0.60  formal Bloom's-taxonomy quizzes
--   * mini_quiz_score        → 0.20  micro-lesson concept checks
--   * completion_score       → 0.10  micro-lesson completion ratio
--   * engagement_score       → 0.10  flashcard / Ask-AI engagement
--
-- Mastery = sum(component * weight). Range: 0.0 — 1.0.

CREATE TABLE IF NOT EXISTS knowledge_node_mastery (
    user_id              BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id            BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    node_id              BIGINT NOT NULL,
    formal_quiz_score    DOUBLE PRECISION NOT NULL DEFAULT 0,
    formal_quiz_count    INT              NOT NULL DEFAULT 0,
    mini_quiz_score      DOUBLE PRECISION NOT NULL DEFAULT 0,
    mini_quiz_count      INT              NOT NULL DEFAULT 0,
    completion_score     DOUBLE PRECISION NOT NULL DEFAULT 0,
    completion_count     INT              NOT NULL DEFAULT 0,
    engagement_score     DOUBLE PRECISION NOT NULL DEFAULT 0,
    engagement_count     INT              NOT NULL DEFAULT 0,
    mastery_level        DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_interaction_at  TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, course_id, node_id)
);

CREATE INDEX IF NOT EXISTS idx_knm_course_node ON knowledge_node_mastery(course_id, node_id);
CREATE INDEX IF NOT EXISTS idx_knm_user_course ON knowledge_node_mastery(user_id, course_id);
