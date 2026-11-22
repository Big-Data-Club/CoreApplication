-- Additive safety metadata. Apply before deploying the matching LMS image.
CREATE TABLE IF NOT EXISTS lms_callback_receipts (
 kind TEXT NOT NULL,
 job_id BIGINT NOT NULL,
 payload_hash TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(kind,job_id)
);
CREATE TABLE IF NOT EXISTS lms_processed_interactions (
 interaction_id BIGINT PRIMARY KEY,
 processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS lms_file_assets (
 file_path TEXT PRIMARY KEY,
 owner_user_id BIGINT NOT NULL CHECK(owner_user_id>0),
 size_bytes BIGINT NOT NULL CHECK(size_bytes>=0),
 visibility TEXT NOT NULL DEFAULT 'private' CHECK (visibility IN ('private','public')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_lms_file_assets_owner ON lms_file_assets(owner_user_id);
CREATE TABLE IF NOT EXISTS lms_quiz_effects (
 attempt_id BIGINT PRIMARY KEY REFERENCES quiz_attempts(id) ON DELETE CASCADE,
 available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 local_completed_at TIMESTAMPTZ,
 completed_at TIMESTAMPTZ,
 attempts INTEGER NOT NULL DEFAULT 0,
 last_error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_lms_quiz_effects_pending ON lms_quiz_effects(available_at) WHERE completed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_lms_quiz_effects_local ON lms_quiz_effects(attempt_id) WHERE local_completed_at IS NULL;
