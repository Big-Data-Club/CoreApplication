-- V012: User feedback on individual assistant messages.
-- Feeds offline quality evaluation (grounding / helpfulness signals).
CREATE TABLE IF NOT EXISTS agent_message_feedback (
    id          BIGSERIAL PRIMARY KEY,
    message_id  BIGINT NOT NULL REFERENCES agent_messages(id) ON DELETE CASCADE,
    session_id  UUID NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    user_id     BIGINT NOT NULL,
    rating      VARCHAR(10) NOT NULL CHECK (rating IN ('like', 'dislike')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_feedback_message_user UNIQUE (message_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_feedback_session
    ON agent_message_feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_feedback_recent
    ON agent_message_feedback(user_id, created_at DESC);
