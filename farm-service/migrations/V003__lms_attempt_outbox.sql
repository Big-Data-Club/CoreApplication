CREATE TABLE IF NOT EXISTS game_learning_outbox (
 challenge_id UUID PRIMARY KEY REFERENCES farm_answers(challenge_id),
 payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 delivered_at TIMESTAMPTZ,
 next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 attempts INT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS game_learning_outbox_pending_idx ON game_learning_outbox(next_attempt_at,created_at) WHERE delivered_at IS NULL;
