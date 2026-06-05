-- Section overview generation jobs
CREATE TABLE IF NOT EXISTS section_overview_jobs (
    id            BIGSERIAL PRIMARY KEY,
    section_id    BIGINT      NOT NULL,
    course_id     BIGINT      NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'queued',
    progress      INT         NOT NULL DEFAULT 0,
    stage         TEXT        NOT NULL DEFAULT '',
    error_msg     TEXT        NOT NULL DEFAULT '',
    language      TEXT        NOT NULL DEFAULT 'vi',
    question_count INT        NOT NULL DEFAULT 10,
    created_by    BIGINT      NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Generated overview lessons (draft)
CREATE TABLE IF NOT EXISTS section_overview_lessons (
    id                   BIGSERIAL PRIMARY KEY,
    job_id               BIGINT      NOT NULL REFERENCES section_overview_jobs(id) ON DELETE CASCADE,
    section_id           BIGINT      NOT NULL,
    course_id            BIGINT      NOT NULL,
    title                TEXT        NOT NULL DEFAULT '',
    summary              TEXT        NOT NULL DEFAULT '',
    markdown_content     TEXT        NOT NULL DEFAULT '',
    references_json      JSONB       NOT NULL DEFAULT '[]',
    status               TEXT        NOT NULL DEFAULT 'draft',
    published_content_id BIGINT,
    created_by           BIGINT      NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Generated overview quizzes (draft)
CREATE TABLE IF NOT EXISTS section_overview_quizzes (
    id                BIGSERIAL PRIMARY KEY,
    job_id            BIGINT      NOT NULL REFERENCES section_overview_jobs(id) ON DELETE CASCADE,
    section_id        BIGINT      NOT NULL,
    course_id         BIGINT      NOT NULL,
    title             TEXT        NOT NULL DEFAULT '',
    summary           TEXT        NOT NULL DEFAULT '',
    question_count    INT         NOT NULL DEFAULT 10,
    questions_json    JSONB       NOT NULL DEFAULT '[]',
    references_json   JSONB       NOT NULL DEFAULT '[]',
    status            TEXT        NOT NULL DEFAULT 'draft',
    published_quiz_id BIGINT,
    created_by        BIGINT      NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sov_jobs_section ON section_overview_jobs(section_id);
CREATE INDEX IF NOT EXISTS idx_sov_jobs_course  ON section_overview_jobs(course_id);
CREATE INDEX IF NOT EXISTS idx_sov_lessons_job  ON section_overview_lessons(job_id);
CREATE INDEX IF NOT EXISTS idx_sov_quizzes_job  ON section_overview_quizzes(job_id);
