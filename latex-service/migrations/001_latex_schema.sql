-- ============================================
--  BDCTex Core Schema
-- ============================================

-- Projects
CREATE TABLE IF NOT EXISTS latex_projects (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL,
    title           VARCHAR(255) NOT NULL,
    description     TEXT DEFAULT '',
    compiler        VARCHAR(20) NOT NULL DEFAULT 'pdflatex',
    main_file       VARCHAR(255) NOT NULL DEFAULT 'main.tex',
    template_id     VARCHAR(50) DEFAULT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_compiler CHECK (compiler IN ('pdflatex', 'xelatex', 'lualatex'))
);

CREATE INDEX IF NOT EXISTS idx_projects_user_active ON latex_projects(user_id, updated_at DESC)
    WHERE status = 'active';

-- Project files (metadata — actual content in MinIO)
CREATE TABLE IF NOT EXISTS latex_project_files (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES latex_projects(id) ON DELETE CASCADE,
    filename        VARCHAR(500) NOT NULL,
    filepath        VARCHAR(1000) NOT NULL,       -- MinIO object key
    file_size       BIGINT NOT NULL DEFAULT 0,
    mime_type       VARCHAR(100) NOT NULL DEFAULT 'text/plain',
    content_hash    VARCHAR(64),                   -- SHA-256 for dedup/change detection
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(project_id, filename)
);

CREATE INDEX IF NOT EXISTS idx_files_project ON latex_project_files(project_id);

-- Compilation history
CREATE TABLE IF NOT EXISTS latex_compilations (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES latex_projects(id) ON DELETE CASCADE,
    user_id         BIGINT NOT NULL,
    job_id          VARCHAR(36) NOT NULL UNIQUE,   -- UUID for polling
    compiler        VARCHAR(20) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'queued',
    pdf_path        VARCHAR(1000),                 -- MinIO key of output PDF
    log_output      TEXT,                           -- Compilation log
    error_message   TEXT,
    duration_ms     INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,

    CONSTRAINT chk_comp_status CHECK (status IN ('queued','compiling','success','failed','timeout'))
);

CREATE INDEX IF NOT EXISTS idx_compilations_project ON latex_compilations(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_compilations_job ON latex_compilations(job_id);
CREATE INDEX IF NOT EXISTS idx_compilations_active ON latex_compilations(status)
    WHERE status IN ('queued', 'compiling');
