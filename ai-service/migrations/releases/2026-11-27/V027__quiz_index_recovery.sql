-- Forward-only recovery metadata; retain on rollback.
ALTER TABLE quiz_index_jobs ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE quiz_index_jobs ADD COLUMN IF NOT EXISTS retry_at TIMESTAMPTZ;
ALTER TABLE quiz_index_jobs ADD COLUMN IF NOT EXISTS last_error_code TEXT;
CREATE INDEX IF NOT EXISTS quiz_index_recovery_due
    ON quiz_index_jobs(status, retry_at, updated_at)
    WHERE status IN ('pending', 'processing', 'failed');
