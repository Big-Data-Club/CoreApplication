-- ═══════════════════════════════════════════════════════════════
-- Lab Service Core Schema
-- ═══════════════════════════════════════════════════════════════

-- Users (synced from Auth, identical to LMS pattern)
CREATE TABLE IF NOT EXISTS users (
    id          BIGINT PRIMARY KEY,
    email       VARCHAR(255) NOT NULL UNIQUE,
    full_name   VARCHAR(255) NOT NULL DEFAULT '',
    roles       TEXT[]       NOT NULL DEFAULT '{}',
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    synced_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════
-- Environment Templates
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS environment_templates (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    description     TEXT DEFAULT '',
    compute_backend VARCHAR(20)  NOT NULL DEFAULT 'K8S'
                    CHECK (compute_backend IN ('K8S', 'SLURM')),
    docker_image    VARCHAR(500) NOT NULL DEFAULT 'ubuntu:22.04',
    cpu_milli       INT          NOT NULL DEFAULT 500,
    memory_mb       INT          NOT NULL DEFAULT 512,
    gpu_count       INT          NOT NULL DEFAULT 0,
    disk_size_mb    INT          NOT NULL DEFAULT 1024,
    allowed_ports   JSONB        DEFAULT '[]',
    startup_script  TEXT         DEFAULT '',
    packages        JSONB        DEFAULT '[]',
    slurm_partition VARCHAR(100) DEFAULT '',
    slurm_account   VARCHAR(100) DEFAULT '',
    slurm_qos       VARCHAR(100) DEFAULT '',
    slurm_max_time  VARCHAR(20)  DEFAULT '01:00:00',
    created_by      BIGINT       NOT NULL REFERENCES users(id),
    is_public       BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════
-- Labs (unified, lab_type determines runtime)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS labs (
    id                       BIGSERIAL PRIMARY KEY,
    title                    VARCHAR(255) NOT NULL,
    description              TEXT DEFAULT '',
    category                 VARCHAR(100) DEFAULT '',
    level                    VARCHAR(30)  DEFAULT 'BEGINNER'
                             CHECK (level IN ('BEGINNER','INTERMEDIATE','ADVANCED','ALL_LEVELS')),
    thumbnail_url            VARCHAR(500) DEFAULT '',
    lab_type                 VARCHAR(30) NOT NULL DEFAULT 'CODING'
                             CHECK (lab_type IN (
                                 'CODING', 'HPC', 'JUPYTER',
                                 'WORKSPACE', 'DATABASE', 'CUSTOM'
                             )),
    status                   VARCHAR(20)  NOT NULL DEFAULT 'DRAFT'
                             CHECK (status IN ('DRAFT','PUBLISHED','ARCHIVED')),
    runtime_config           JSONB NOT NULL DEFAULT '{}',
    environment_template_id  BIGINT REFERENCES environment_templates(id),
    max_session_duration_min INT  NOT NULL DEFAULT 120,
    max_concurrent_sessions  INT  NOT NULL DEFAULT 50,
    max_submissions          INT  DEFAULT NULL,
    auto_grade               BOOLEAN NOT NULL DEFAULT FALSE,
    grading_config           JSONB DEFAULT '{}',
    start_time               TIMESTAMP,
    deadline                 TIMESTAMP,
    allow_late_submission    BOOLEAN DEFAULT FALSE,
    late_penalty_percent     INT DEFAULT 0,
    created_by               BIGINT NOT NULL REFERENCES users(id),
    published_at             TIMESTAMP,
    created_at               TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_labs_status ON labs(status);
CREATE INDEX idx_labs_type   ON labs(lab_type);
CREATE INDEX idx_labs_creator ON labs(created_by);

-- ═══════════════════════════════════════════════════════════════
-- Lab Sections (mirrors course sections)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS lab_sections (
    id           BIGSERIAL PRIMARY KEY,
    lab_id       BIGINT       NOT NULL REFERENCES labs(id) ON DELETE CASCADE,
    title        VARCHAR(255) NOT NULL,
    description  TEXT         DEFAULT '',
    order_index  INT          NOT NULL DEFAULT 0,
    is_published BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sections_lab ON lab_sections(lab_id, order_index);

-- ═══════════════════════════════════════════════════════════════
-- Lab Section Content
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS lab_section_content (
    id           BIGSERIAL PRIMARY KEY,
    section_id   BIGINT       NOT NULL REFERENCES lab_sections(id) ON DELETE CASCADE,
    type         VARCHAR(30)  NOT NULL
                 CHECK (type IN ('TEXT','DOCUMENT','IMAGE','CODE_TEMPLATE','CHECKPOINT')),
    title        VARCHAR(255) NOT NULL,
    description  TEXT         DEFAULT '',
    order_index  INT          NOT NULL DEFAULT 0,
    metadata     JSONB        DEFAULT '{}',
    is_published BOOLEAN      NOT NULL DEFAULT FALSE,
    is_mandatory BOOLEAN      NOT NULL DEFAULT FALSE,
    file_path    VARCHAR(500) DEFAULT '',
    file_size    BIGINT       DEFAULT 0,
    file_type    VARCHAR(50)  DEFAULT '',
    created_by   BIGINT       NOT NULL REFERENCES users(id),
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_content_section ON lab_section_content(section_id, order_index);

-- ═══════════════════════════════════════════════════════════════
-- Lab Enrollments (mirrors course enrollments)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS lab_enrollments (
    id          BIGSERIAL PRIMARY KEY,
    lab_id      BIGINT       NOT NULL REFERENCES labs(id) ON DELETE CASCADE,
    user_id     BIGINT       NOT NULL REFERENCES users(id),
    status      VARCHAR(20)  NOT NULL DEFAULT 'ACCEPTED'
                CHECK (status IN ('WAITING','ACCEPTED','REJECTED')),
    enrolled_at TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE(lab_id, user_id)
);

CREATE INDEX idx_enrollments_user ON lab_enrollments(user_id);

-- ═══════════════════════════════════════════════════════════════
-- Lab Sessions (runtime containers — WORKSPACE/JUPYTER labs)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS lab_sessions (
    id                 BIGSERIAL PRIMARY KEY,
    lab_id             BIGINT       NOT NULL REFERENCES labs(id),
    user_id            BIGINT       NOT NULL REFERENCES users(id),
    session_token      UUID         NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    k8s_pod_name       VARCHAR(253) DEFAULT '',
    k8s_namespace      VARCHAR(63)  DEFAULT '',
    k8s_node           VARCHAR(253) DEFAULT '',
    k8s_pod_ip         VARCHAR(45)  DEFAULT '',
    ttyd_port          INT          DEFAULT 7681,
    status             VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                       CHECK (status IN (
                           'PENDING','CREATING','RUNNING',
                           'SUSPENDED','STOPPING','STOPPED',
                           'FAILED','COMPLETED'
                       )),
    started_at         TIMESTAMP,
    last_active_at     TIMESTAMP    DEFAULT NOW(),
    suspended_at       TIMESTAMP,
    ended_at           TIMESTAMP,
    expires_at         TIMESTAMP,
    workspace_snapshot  VARCHAR(500) DEFAULT '',
    created_at         TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sessions_user_lab ON lab_sessions(user_id, lab_id);
CREATE INDEX idx_sessions_status   ON lab_sessions(status)
    WHERE status IN ('RUNNING','PENDING','CREATING');

-- ═══════════════════════════════════════════════════════════════
-- Workspace Files (dedup via content hash)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS workspace_files (
    id            BIGSERIAL PRIMARY KEY,
    session_id    BIGINT       NOT NULL REFERENCES lab_sessions(id) ON DELETE CASCADE,
    user_id       BIGINT       NOT NULL REFERENCES users(id),
    file_path     VARCHAR(1000) NOT NULL,
    minio_key     VARCHAR(500)  NOT NULL,
    content_hash  VARCHAR(64)   NOT NULL,
    file_size     BIGINT        NOT NULL DEFAULT 0,
    version       INT           NOT NULL DEFAULT 1,
    created_at    TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP     NOT NULL DEFAULT NOW(),
    UNIQUE(session_id, file_path)
);

CREATE INDEX idx_workspace_hash ON workspace_files(content_hash);
