-- Private object manifests outlive project deletion so cleanup cannot orphan media.
CREATE TABLE studio_temporary_media (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    generation TEXT NOT NULL,
    owner_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    object_key TEXT NOT NULL UNIQUE,
    storage_bucket TEXT NOT NULL,
    media_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    ready_at TIMESTAMPTZ,
    -- NULL only after a successfully stored persistent source/PDF is ready.
    expires_at TIMESTAMPTZ DEFAULT now() + interval '3 hours',
    deleted_at TIMESTAMPTZ,
    cleanup_attempts INT NOT NULL DEFAULT 0,
    cleanup_after TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX studio_media_expiry ON studio_temporary_media(expires_at, cleanup_after) WHERE deleted_at IS NULL;
CREATE INDEX studio_media_project ON studio_temporary_media(project_id, generation);
CREATE TABLE studio_legacy_media_swept (project_id UUID PRIMARY KEY);

-- Shared-channel credentials survive frontend restarts; ciphertext only at rest.
CREATE TABLE studio_shared_youtube_connection (
    singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK (singleton),
    encrypted_connection TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE studio_youtube_uploads (
    id UUID PRIMARY KEY,
    asset_id UUID NOT NULL UNIQUE REFERENCES studio_temporary_media(id),
    owner_id BIGINT NOT NULL,
    channel_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    privacy TEXT NOT NULL CHECK (privacy IN ('private','unlisted','public')),
    made_for_kids BOOLEAN NOT NULL,
    contains_synthetic_media BOOLEAN NOT NULL DEFAULT true,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','ready','failed')),
    encrypted_session TEXT,
    video_id TEXT,
    actual_privacy TEXT,
    processing_status TEXT,
    error TEXT,
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    attempts INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX studio_youtube_queue ON studio_youtube_uploads(status, lease_until, created_at);

-- Recoverable external-client writes (no duplicate decks/cards on transport retry).
CREATE TABLE mcp_authoring_requests (
    owner_id BIGINT NOT NULL,
    request_id UUID NOT NULL,
    operation TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    result JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(owner_id, request_id)
);
