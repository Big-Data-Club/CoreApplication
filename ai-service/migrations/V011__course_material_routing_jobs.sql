CREATE TABLE IF NOT EXISTS course_material_routing_jobs (
    id UUID PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PROCESSING'
        CHECK (status IN ('PROCESSING','READY','FAILED','CANCELLED')),
    documents JSONB NOT NULL,
    sections JSONB NOT NULL,
    suggestions JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message TEXT,
    lease_owner VARCHAR(255),
    lease_until TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_material_routing_recovery
    ON course_material_routing_jobs(status, lease_until, updated_at)
    WHERE status='PROCESSING';
