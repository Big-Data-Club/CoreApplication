-- Apply to the Auth-owned database BEFORE enabling FARM_REWARDS_ENABLED.
-- Hibernate ddl-auto=update also creates the mapped table in local development.
CREATE TABLE IF NOT EXISTS farm_score_receipts (
 event_id UUID PRIMARY KEY,
 harvest_id UUID NOT NULL UNIQUE,
 user_id BIGINT NOT NULL,
 delta INTEGER NOT NULL CHECK (delta = 5),
 occurred_at TIMESTAMPTZ NOT NULL,
 applied_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS farm_score_receipts_user_idx ON farm_score_receipts(user_id);
