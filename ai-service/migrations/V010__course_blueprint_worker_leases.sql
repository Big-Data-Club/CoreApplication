-- Durable worker ownership.  Kafka is a delivery signal; these fields make
-- execution recoverable and idempotent across pod restarts and redeployments.
ALTER TABLE course_blueprints
    ADD COLUMN IF NOT EXISTS processing_stage VARCHAR(32) NOT NULL DEFAULT 'QUEUED',
    ADD COLUMN IF NOT EXISTS progress_pct SMALLINT NOT NULL DEFAULT 0
        CHECK (progress_pct >= 0 AND progress_pct <= 100),
    ADD COLUMN IF NOT EXISTS lease_owner VARCHAR(255),
    ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_course_blueprints_recovery
    ON course_blueprints (status, lease_until, updated_at)
    WHERE status = 'PROCESSING';
