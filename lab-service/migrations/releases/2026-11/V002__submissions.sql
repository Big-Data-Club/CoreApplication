-- ═══════════════════════════════════════════════════════════════
-- Lab Service Submission Schema
-- ═══════════════════════════════════════════════════════════════

-- Test Cases (for CODING and DATABASE labs)
CREATE TABLE IF NOT EXISTS lab_test_cases (
    id             BIGSERIAL PRIMARY KEY,
    lab_id         BIGINT NOT NULL REFERENCES labs(id) ON DELETE CASCADE,
    name           VARCHAR(255) NOT NULL DEFAULT '',
    order_index    INT NOT NULL DEFAULT 0,
    is_sample      BOOLEAN NOT NULL DEFAULT FALSE,
    is_hidden      BOOLEAN NOT NULL DEFAULT TRUE,
    weight         INT NOT NULL DEFAULT 1,
    input          TEXT DEFAULT '',
    expected       TEXT DEFAULT '',
    query_expected TEXT DEFAULT '',
    time_limit_ms  INT DEFAULT NULL,
    memory_limit_mb INT DEFAULT NULL,
    explanation    TEXT DEFAULT '',
    created_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_test_cases_lab ON lab_test_cases(lab_id, order_index);

-- ═══════════════════════════════════════════════════════════════
-- Unified Submissions
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS lab_submissions (
    id              BIGSERIAL PRIMARY KEY,
    lab_id          BIGINT NOT NULL REFERENCES labs(id),
    user_id         BIGINT NOT NULL REFERENCES users(id),
    session_id      BIGINT REFERENCES lab_sessions(id),
    language        VARCHAR(30)  DEFAULT '',
    code            TEXT DEFAULT '',
    query           TEXT DEFAULT '',
    files_snapshot  VARCHAR(500) DEFAULT '',
    notebook_key    VARCHAR(500) DEFAULT '',
    script_content  TEXT DEFAULT '',
    status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN (
                        'PENDING','RUNNING','ACCEPTED','WRONG_ANSWER',
                        'TIME_LIMIT','MEMORY_LIMIT','RUNTIME_ERROR',
                        'COMPILE_ERROR','COMPLETED','FAILED','CANCELLED'
                    )),
    score           DECIMAL(7,2) DEFAULT 0,
    max_score       DECIMAL(7,2) DEFAULT 100,
    passed_tests    INT DEFAULT 0,
    total_tests     INT DEFAULT 0,
    runtime_ms      INT DEFAULT 0,
    memory_kb       INT DEFAULT 0,
    slurm_job_id    BIGINT,
    stdout_key      VARCHAR(500) DEFAULT '',
    stderr_key      VARCHAR(500) DEFAULT '',
    exit_code       INT,
    feedback        JSONB DEFAULT '{}',
    compiler_output TEXT DEFAULT '',
    submitted_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    graded_at       TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_submissions_lab_user ON lab_submissions(lab_id, user_id);
CREATE INDEX idx_submissions_status   ON lab_submissions(status);

-- ═══════════════════════════════════════════════════════════════
-- Submission Test Results (per test case)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS submission_test_results (
    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL REFERENCES lab_submissions(id) ON DELETE CASCADE,
    test_case_id    BIGINT NOT NULL REFERENCES lab_test_cases(id),
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN (
                        'PENDING','PASSED','WRONG_ANSWER',
                        'TIME_LIMIT','MEMORY_LIMIT','RUNTIME_ERROR'
                    )),
    actual_output   TEXT DEFAULT '',
    runtime_ms      INT DEFAULT 0,
    memory_kb       INT DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_test_results_sub ON submission_test_results(submission_id);

-- ═══════════════════════════════════════════════════════════════
-- Leaderboard
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS lab_leaderboard (
    id                  BIGSERIAL PRIMARY KEY,
    lab_id              BIGINT NOT NULL REFERENCES labs(id),
    user_id             BIGINT NOT NULL REFERENCES users(id),
    best_submission_id  BIGINT REFERENCES lab_submissions(id),
    best_score          DECIMAL(7,2) DEFAULT 0,
    best_runtime_ms     INT DEFAULT 0,
    best_memory_kb      INT DEFAULT 0,
    attempt_count       INT DEFAULT 0,
    first_accepted_at   TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(lab_id, user_id)
);

CREATE INDEX idx_leaderboard_score ON lab_leaderboard(lab_id, best_score DESC, best_runtime_ms ASC);

-- ═══════════════════════════════════════════════════════════════
-- Datasets
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS datasets (
    id           BIGSERIAL PRIMARY KEY,
    name         VARCHAR(255) NOT NULL,
    description  TEXT DEFAULT '',
    minio_key    VARCHAR(500) NOT NULL,
    file_size    BIGINT DEFAULT 0,
    format       VARCHAR(50) DEFAULT '',
    is_public    BOOLEAN DEFAULT FALSE,
    created_by   BIGINT NOT NULL REFERENCES users(id),
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lab_datasets (
    lab_id       BIGINT NOT NULL REFERENCES labs(id) ON DELETE CASCADE,
    dataset_id   BIGINT NOT NULL REFERENCES datasets(id),
    mount_path   VARCHAR(500) NOT NULL DEFAULT '/data',
    PRIMARY KEY (lab_id, dataset_id)
);
