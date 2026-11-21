CREATE TABLE block_activity (
  page_id uuid NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  block_id text NOT NULL,
  actor_id text NOT NULL REFERENCES workspace_users(id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(page_id,block_id)
);
