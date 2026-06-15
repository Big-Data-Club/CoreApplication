-- ── Add is_dm Column to chat_channels ───────────────────────────
ALTER TABLE chat_channels ADD COLUMN IF NOT EXISTS is_dm BOOLEAN NOT NULL DEFAULT false;

-- Create index for is_dm
CREATE INDEX IF NOT EXISTS idx_channels_is_dm ON chat_channels(is_dm);
