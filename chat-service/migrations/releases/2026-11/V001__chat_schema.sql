-- ============================================================
-- Chat Service - V001 Database Schema
-- Designed for Neon PostgreSQL (serverless / pgx stdlib)
-- ============================================================

-- ── Users (synced from auth-and-management-service) ──────────
CREATE TABLE IF NOT EXISTS users (
    id              BIGINT PRIMARY KEY,          -- same ID as auth-service
    email           VARCHAR(255) UNIQUE NOT NULL,
    full_name       VARCHAR(255) NOT NULL DEFAULT '',
    profile_picture VARCHAR(500),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Chat Channels ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_channels (
    id          BIGSERIAL PRIMARY KEY,
    slug        VARCHAR(80)  UNIQUE NOT NULL,
    name        VARCHAR(120) NOT NULL,
    description TEXT,
    is_private  BOOLEAN NOT NULL DEFAULT false,
    created_by  BIGINT  NOT NULL REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Per-channel Role Access Control ───────────────────────────
-- role_name matches roles from JWT (e.g. "ADMIN","TEACHER","STUDENT")
CREATE TABLE IF NOT EXISTS chat_channel_roles (
    channel_id BIGINT       NOT NULL REFERENCES chat_channels(id) ON DELETE CASCADE,
    role_name  VARCHAR(80)  NOT NULL,
    can_read   BOOLEAN NOT NULL DEFAULT true,
    can_write  BOOLEAN NOT NULL DEFAULT true,
    PRIMARY KEY (channel_id, role_name)
);

-- ── Per-channel User Whitelist (explicit override) ─────────────
CREATE TABLE IF NOT EXISTS chat_channel_users (
    channel_id BIGINT NOT NULL REFERENCES chat_channels(id) ON DELETE CASCADE,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (channel_id, user_id)
);

-- ── Messages ──────────────────────────────────────────────────
-- is_deleted = soft delete; body retained for audit,
-- shown as "[deleted]" on the client.
CREATE TABLE IF NOT EXISTS chat_messages (
    id         BIGSERIAL PRIMARY KEY,
    channel_id BIGINT    NOT NULL REFERENCES chat_channels(id) ON DELETE CASCADE,
    sender_id  BIGINT    NOT NULL REFERENCES users(id),
    body       TEXT      NOT NULL CHECK (char_length(body) BETWEEN 1 AND 4000),
    is_deleted BOOLEAN   NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────
-- Cursor-based pagination on messages (channel + time, DESC)
CREATE INDEX IF NOT EXISTS idx_messages_channel_created
    ON chat_messages (channel_id, created_at DESC)
    WHERE is_deleted = false;

-- Full index for admin/history queries
CREATE INDEX IF NOT EXISTS idx_messages_channel_all
    ON chat_messages (channel_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_channel_roles_channel
    ON chat_channel_roles (channel_id);

CREATE INDEX IF NOT EXISTS idx_channel_users_user
    ON chat_channel_users (user_id);

CREATE INDEX IF NOT EXISTS idx_users_email
    ON users (email);

-- ── Triggers: updated_at ─────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER trg_channels_updated_at
    BEFORE UPDATE ON chat_channels
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER trg_messages_updated_at
    BEFORE UPDATE ON chat_messages
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
