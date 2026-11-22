-- V014: hashed, scoped MCP credentials and a minimal audit trail.
-- Raw bearer tokens are displayed once and are never persisted.

CREATE TABLE IF NOT EXISTS mcp_api_keys (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL,
    name         VARCHAR(100) NOT NULL DEFAULT 'MCP Key',
    key_hash     CHAR(64) NOT NULL UNIQUE,
    key_prefix   VARCHAR(20) NOT NULL,
    scopes       TEXT[] NOT NULL DEFAULT ARRAY['read']::TEXT[],
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    revoked_at   TIMESTAMPTZ,
    CONSTRAINT mcp_api_keys_scopes_valid
        CHECK (scopes <@ ARRAY['read', 'write']::TEXT[])
);

CREATE INDEX IF NOT EXISTS idx_mcp_api_keys_hash_active
    ON mcp_api_keys(key_hash) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_mcp_api_keys_user ON mcp_api_keys(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS mcp_audit_log (
    id          BIGSERIAL PRIMARY KEY,
    key_id      BIGINT REFERENCES mcp_api_keys(id) ON DELETE SET NULL,
    user_id     BIGINT NOT NULL,
    action      VARCHAR(160) NOT NULL,
    success     BOOLEAN NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mcp_audit_user_created
    ON mcp_audit_log(user_id, created_at DESC);
