-- A course blueprint is a reviewable, immutable-at-approval planning artefact.
-- The LMS remains the source of truth for courses/content; this table keeps the
-- AI proposal, its source provenance, and validation report together.
CREATE TABLE IF NOT EXISTS course_blueprints (
    id UUID PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    origin VARCHAR(20) NOT NULL DEFAULT 'course_create'
        CHECK (origin IN ('course_create', 'chatbot')),
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'APPROVED', 'CANCELLED', 'APPLIED', 'FAILED')),
    source_manifest JSONB NOT NULL,
    -- Values issued by LMS after its membership/permission check.  Kept with
    -- the draft so later teacher edits can be validated without trusting AI.
    governance_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    plan JSONB NOT NULL,
    validation_report JSONB NOT NULL DEFAULT '{}'::jsonb,
    version INTEGER NOT NULL DEFAULT 1,
    applied_course_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_course_blueprints_owner_status
    ON course_blueprints(owner_id, status, updated_at DESC);

DROP TRIGGER IF EXISTS tr_course_blueprints_updated ON course_blueprints;
CREATE TRIGGER tr_course_blueprints_updated
    BEFORE UPDATE ON course_blueprints
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
