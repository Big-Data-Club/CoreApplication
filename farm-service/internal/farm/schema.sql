CREATE TABLE IF NOT EXISTS farm_states (
 user_id BIGINT PRIMARY KEY CHECK (user_id > 0),
 state JSONB NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS farm_answers (
 challenge_id UUID PRIMARY KEY,
 user_id BIGINT NOT NULL,
 result JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS farm_answers_user_idx ON farm_answers(user_id);
CREATE TABLE IF NOT EXISTS farm_outbox (
 event_id UUID PRIMARY KEY,
 user_id BIGINT NOT NULL,
 payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 published_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS farm_outbox_pending_idx ON farm_outbox(created_at) WHERE published_at IS NULL;
CREATE INDEX IF NOT EXISTS farm_outbox_pending_user_idx ON farm_outbox(user_id) WHERE published_at IS NULL;
