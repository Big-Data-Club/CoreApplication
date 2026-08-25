-- V017: Question Bank (Thư viện đề thi) per course.
-- Teachers accumulate reusable, classified questions; quizzes are assembled
-- from this pool. node_id is intentionally nullable -> "dangling" items are
-- first-class citizens (imported from documents without a graph match yet).
--
-- Modeling notes:
--  * answer_options / correct_answers / settings are stored as JSONB so a
--    bank item mirrors the exact CreateQuestionRequest contract used by
--    POST /quizzes/{id}/questions/batch - promotion into a quiz is a pure
--    copy without shape conversion.
--  * source tracks provenance for analytics (manual | import | ai_generated).
--  * status supports review workflows later (draft/approved/disabled).

CREATE TABLE IF NOT EXISTS question_bank_items (
    id             BIGSERIAL PRIMARY KEY,
    course_id      BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    -- Loose reference into the AI service's knowledge graph (same convention
    -- as quiz_questions.node_id - no FK across service DBs).
    node_id        BIGINT,
    source_quiz_id BIGINT REFERENCES quizzes(id) ON DELETE SET NULL,

    question_type  VARCHAR(50) NOT NULL CHECK (question_type IN (
        'SINGLE_CHOICE','MULTIPLE_CHOICE','SHORT_ANSWER','ESSAY',
        'FILE_UPLOAD','FILL_BLANK_TEXT','FILL_BLANK_DROPDOWN')),
    question_text  TEXT NOT NULL,
    explanation    TEXT,
    points         DECIMAL(10,2) NOT NULL DEFAULT 10.00 CHECK (points >= 0),
    bloom_level    VARCHAR(20) CHECK (bloom_level IN
        ('remember','understand','apply','analyze','evaluate','create')),
    difficulty     VARCHAR(20) NOT NULL DEFAULT 'MEDIUM' CHECK (difficulty IN
        ('EASY','MEDIUM','HARD')),

    answer_options JSONB NOT NULL DEFAULT '[]'::jsonb,
    correct_answers JSONB NOT NULL DEFAULT '[]'::jsonb,
    settings       JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags           TEXT[] NOT NULL DEFAULT '{}',

    source         VARCHAR(20) NOT NULL DEFAULT 'MANUAL' CHECK (source IN
        ('MANUAL','IMPORT','AI_GENERATED')),
    status         VARCHAR(20) NOT NULL DEFAULT 'APPROVED' CHECK (status IN
        ('DRAFT','APPROVED','DISABLED')),

    created_by     BIGINT NOT NULL REFERENCES users(id),
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- List/filter hot path: course scope + recency cursor.
CREATE INDEX IF NOT EXISTS idx_qbank_course_created
    ON question_bank_items(course_id, created_at DESC, id DESC);
-- Node filter incl. dangling lookups.
CREATE INDEX IF NOT EXISTS idx_qbank_course_node
    ON question_bank_items(course_id, node_id);
-- Difficulty / bloom facets.
CREATE INDEX IF NOT EXISTS idx_qbank_course_difficulty
    ON question_bank_items(course_id, difficulty);
CREATE INDEX IF NOT EXISTS idx_qbank_course_bloom
    ON question_bank_items(course_id, bloom_level);
-- Full-text search over question text (no extension dependency).
CREATE INDEX IF NOT EXISTS idx_qbank_fts
    ON question_bank_items USING gin (to_tsvector('simple', question_text));
