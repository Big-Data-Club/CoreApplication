-- ── MICRO QUIZ JOBS ──────────────────────────────────────────────
-- One job produces many micro quizzes (one per knowledge node).
-- Same lifecycle as micro_lesson_jobs: queued → processing → completed/failed.

CREATE TABLE IF NOT EXISTS micro_quiz_jobs (
    id                BIGSERIAL PRIMARY KEY,
    course_id         BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    section_id        BIGINT REFERENCES course_sections(id) ON DELETE SET NULL,
    source_content_id BIGINT REFERENCES section_content(id) ON DELETE SET NULL,
    source_file_path  VARCHAR(1000),
    source_file_type  VARCHAR(100),
    source_url        VARCHAR(1000),
    language          VARCHAR(10) NOT NULL DEFAULT 'vi',
    status            VARCHAR(20) NOT NULL DEFAULT 'queued'
                          CHECK (status IN ('queued','processing','completed','failed')),
    progress          INT DEFAULT 0,
    stage             VARCHAR(64) DEFAULT '',
    quizzes_count     INT DEFAULT 0,
    error             TEXT,
    created_by        BIGINT NOT NULL REFERENCES users(id),
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at      TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_micro_quiz_jobs_updated_at'
                   AND tgrelid='micro_quiz_jobs'::regclass) THEN
        CREATE TRIGGER update_micro_quiz_jobs_updated_at
            BEFORE UPDATE ON micro_quiz_jobs
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ── MICRO QUIZZES ───────────────────────────────────────────────
-- Each row = one quiz covering one knowledge node.
-- questions_json is the SINGLE SOURCE OF TRUTH for quiz content.
-- Format: [{"question":"...","options":[{"text":"...","is_correct":bool}],
--           "explanation":"...","bloom_level":"remember"}]
-- All text fields inside JSON support Markdown (images, math, etc.)

CREATE TABLE IF NOT EXISTS micro_quizzes (
    id                   BIGSERIAL PRIMARY KEY,
    job_id               BIGINT NOT NULL REFERENCES micro_quiz_jobs(id) ON DELETE CASCADE,
    course_id            BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    section_id           BIGINT REFERENCES course_sections(id) ON DELETE SET NULL,
    source_content_id    BIGINT REFERENCES section_content(id) ON DELETE SET NULL,
    title                VARCHAR(500) NOT NULL,
    summary              TEXT,
    questions_json       JSONB NOT NULL DEFAULT '[]'::jsonb,
    questions_count      INT DEFAULT 0,
    order_index          INT NOT NULL DEFAULT 0,
    status               VARCHAR(20) NOT NULL DEFAULT 'draft'
                             CHECK (status IN ('draft','published','archived')),
    published_content_id BIGINT REFERENCES section_content(id) ON DELETE SET NULL,
    node_id              BIGINT,
    language             VARCHAR(10) DEFAULT 'vi',
    created_by           BIGINT NOT NULL REFERENCES users(id),
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at         TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_micro_quizzes_updated_at'
                   AND tgrelid='micro_quizzes'::regclass) THEN
        CREATE TRIGGER update_micro_quizzes_updated_at
            BEFORE UPDATE ON micro_quizzes
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ── Performance indexes ─────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_mqj_course   ON micro_quiz_jobs(course_id);
CREATE INDEX IF NOT EXISTS idx_mqj_status   ON micro_quiz_jobs(status);
CREATE INDEX IF NOT EXISTS idx_mqj_creator  ON micro_quiz_jobs(created_by);

CREATE INDEX IF NOT EXISTS idx_mq_job       ON micro_quizzes(job_id);
CREATE INDEX IF NOT EXISTS idx_mq_course    ON micro_quizzes(course_id);
CREATE INDEX IF NOT EXISTS idx_mq_section   ON micro_quizzes(section_id);
CREATE INDEX IF NOT EXISTS idx_mq_source    ON micro_quizzes(source_content_id);
CREATE INDEX IF NOT EXISTS idx_mq_status    ON micro_quizzes(status);
CREATE INDEX IF NOT EXISTS idx_mq_order     ON micro_quizzes(job_id, order_index);
CREATE INDEX IF NOT EXISTS idx_mq_node_id   ON micro_quizzes(node_id);

ANALYZE micro_quiz_jobs;
ANALYZE micro_quizzes;
