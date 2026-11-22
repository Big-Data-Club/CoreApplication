CREATE TABLE IF NOT EXISTS speech_jobs (
    id UUID PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    card_id BIGINT NOT NULL REFERENCES personal_flashcards(id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    request JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','ready','failed')),
    object_key TEXT,
    error TEXT,
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    attempts INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(owner_id,content_hash)
);
CREATE INDEX IF NOT EXISTS speech_pending_jobs ON speech_jobs(status,lease_until);
