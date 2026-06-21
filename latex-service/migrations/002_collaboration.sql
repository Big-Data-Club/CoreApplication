-- ============================================
--  BDCTex Collaboration Schema
-- ============================================

-- Project collaborators
CREATE TABLE IF NOT EXISTS latex_project_collaborators (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES latex_projects(id) ON DELETE CASCADE,
    user_id         BIGINT NOT NULL,
    user_email      VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'viewer',
    added_by        BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(project_id, user_id),
    CONSTRAINT chk_collab_role CHECK (role IN ('editor', 'reviewer', 'viewer'))
);

CREATE INDEX IF NOT EXISTS idx_collab_project ON latex_project_collaborators(project_id);
CREATE INDEX IF NOT EXISTS idx_collab_user    ON latex_project_collaborators(user_id);

-- Comments (Overleaf-style: character-offset text selection)
CREATE TABLE IF NOT EXISTS latex_comments (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES latex_projects(id) ON DELETE CASCADE,
    file_id         BIGINT NOT NULL REFERENCES latex_project_files(id) ON DELETE CASCADE,
    user_id         BIGINT NOT NULL,
    user_email      VARCHAR(255) NOT NULL,
    content         TEXT NOT NULL,
    selection_start INT,                    -- character offset start (NULL = general comment)
    selection_end   INT,                    -- character offset end
    selected_text   TEXT,                   -- snapshot of selected text at comment time
    parent_id       BIGINT REFERENCES latex_comments(id) ON DELETE CASCADE,
    resolved        BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_by     BIGINT,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comments_file    ON latex_comments(file_id);
CREATE INDEX IF NOT EXISTS idx_comments_project ON latex_comments(project_id);
CREATE INDEX IF NOT EXISTS idx_comments_thread  ON latex_comments(parent_id) WHERE parent_id IS NOT NULL;

-- Share links (anyone with the token joins the project with the link's role)
CREATE TABLE IF NOT EXISTS latex_share_links (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES latex_projects(id) ON DELETE CASCADE,
    token           VARCHAR(64) NOT NULL UNIQUE,
    role            VARCHAR(20) NOT NULL DEFAULT 'viewer',
    created_by      BIGINT NOT NULL,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_link_role CHECK (role IN ('editor', 'reviewer', 'viewer'))
);

CREATE INDEX IF NOT EXISTS idx_share_links_token   ON latex_share_links(token) WHERE active = TRUE;
CREATE INDEX IF NOT EXISTS idx_share_links_project ON latex_share_links(project_id);
