-- Anonymized, retry-safe teacher analysis results. No learner identities.
CREATE TABLE IF NOT EXISTS quiz_insight_results (
    job_id TEXT PRIMARY KEY,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quiz_insight_results_created_at ON quiz_insight_results(created_at);
