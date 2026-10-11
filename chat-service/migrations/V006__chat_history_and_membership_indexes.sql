-- Cover user-to-channel membership lookup. V001 already provides the
-- (channel_id, id DESC) keyset-history index; do not duplicate it on writes.
CREATE INDEX IF NOT EXISTS idx_chat_channel_users_user_channel
    ON chat_channel_users (user_id, channel_id);
