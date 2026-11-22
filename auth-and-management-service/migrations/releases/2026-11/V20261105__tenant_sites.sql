-- Auth-owned website documents. Apply before deploying tenant-site APIs.
CREATE TABLE IF NOT EXISTS tenant_sites (
  org_id BIGINT PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
  revision BIGINT NOT NULL DEFAULT 0,
  draft TEXT NOT NULL,
  published TEXT,
  published_at TIMESTAMPTZ
);
