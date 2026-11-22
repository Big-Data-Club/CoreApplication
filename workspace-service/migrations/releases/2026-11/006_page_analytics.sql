CREATE TABLE page_visits (
  id bigserial PRIMARY KEY,
  page_id uuid NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  user_id text NOT NULL REFERENCES workspace_users(id),
  viewed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX page_visits_reader ON page_visits(page_id,user_id,viewed_at DESC);
CREATE INDEX page_visits_daily ON page_visits(page_id,viewed_at DESC);
CREATE TABLE page_view_preferences (
  page_id uuid NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  user_id text NOT NULL REFERENCES workspace_users(id),
  show_name boolean NOT NULL DEFAULT false,
  PRIMARY KEY(page_id,user_id)
);
-- Visits start only after this migration and an explicit foreground page-open.
-- Polling metadata, prefetching and opening the analytics panel never add visits.
