-- Studio generation belongs to the worker. Payloads contain owned project IDs,
-- never raw course documents. Leases fence stale workers after pod restarts.
ALTER TABLE studio_projects DROP CONSTRAINT IF EXISTS studio_projects_kind_check;
ALTER TABLE studio_projects ADD CONSTRAINT studio_projects_kind_check
    CHECK (kind IN ('slides','document','report','video'));
ALTER TABLE studio_projects DROP CONSTRAINT IF EXISTS studio_projects_status_check;
ALTER TABLE studio_projects ADD CONSTRAINT studio_projects_status_check
    CHECK (status IN ('collecting','planning','planned','generating','ready','failed'));
ALTER TABLE studio_projects ADD COLUMN IF NOT EXISTS current_job_id UUID;

CREATE TABLE IF NOT EXISTS studio_jobs (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES studio_projects(id) ON DELETE CASCADE,
    owner_id BIGINT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('plan','render')),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','ready','failed')),
    request JSONB NOT NULL DEFAULT '{}',
    checkpoint JSONB NOT NULL DEFAULT '{}',
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    attempts INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS studio_one_active_job ON studio_jobs(project_id)
    WHERE status IN ('queued','running');
CREATE INDEX IF NOT EXISTS studio_pending_jobs ON studio_jobs(status, lease_until, created_at);
