-- AI proposals only; publication remains owned by lab-service.
CREATE TABLE IF NOT EXISTS lab_authoring_jobs (
    id UUID PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUEUED' CHECK(status IN ('QUEUED','RUNNING','READY','FAILED')),
    request JSONB NOT NULL,
    proposal JSONB,
    error TEXT,
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS lab_authoring_jobs_pending ON lab_authoring_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS lab_authoring_jobs_owner ON lab_authoring_jobs(owner_id, created_at DESC);
