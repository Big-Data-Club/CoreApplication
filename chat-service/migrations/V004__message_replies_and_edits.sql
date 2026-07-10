-- ============================================================
-- Chat Service - V004 Message Replies and Edits
-- Adds parent_id for threaded replies and is_edited flag.
-- Both columns use defaults so existing rows are unaffected.
-- ============================================================

-- ── parent_id: nullable FK to the message being replied to ──
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS parent_id BIGINT
        REFERENCES chat_messages(id) ON DELETE SET NULL;

-- ── is_edited: soft flag set when a message body is updated ─
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS is_edited BOOLEAN NOT NULL DEFAULT false;

-- ── Index for efficient "load replies by parent" queries ────
CREATE INDEX IF NOT EXISTS idx_messages_parent_id
    ON chat_messages (parent_id)
    WHERE parent_id IS NOT NULL;
