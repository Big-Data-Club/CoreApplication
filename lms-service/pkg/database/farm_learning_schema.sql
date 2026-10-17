CREATE TABLE IF NOT EXISTS farm_learning_attempts (
    challenge_id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    node_id BIGINT,
    source_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('quiz', 'flashcard')),
    correct BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS farm_learning_attempts_user_course_idx
    ON farm_learning_attempts(user_id, course_id, created_at DESC);
