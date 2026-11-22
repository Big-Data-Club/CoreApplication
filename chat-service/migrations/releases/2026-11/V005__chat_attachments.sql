-- Private attachments are linked to a message and can only be served after
-- chat-service verifies the requester still has channel access.
ALTER TABLE chat_messages DROP CONSTRAINT IF EXISTS chat_messages_body_check;
ALTER TABLE chat_messages
    ADD CONSTRAINT chat_messages_body_length_check
    CHECK (char_length(body) <= 4000);

CREATE TABLE IF NOT EXISTS chat_attachments (
    id           VARCHAR(64) PRIMARY KEY,
    message_id   BIGINT NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    object_key   VARCHAR(512) NOT NULL UNIQUE,
    file_name    VARCHAR(255) NOT NULL,
    mime_type    VARCHAR(150) NOT NULL,
    size_bytes   BIGINT NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 20971520),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_attachments_message
    ON chat_attachments(message_id);
