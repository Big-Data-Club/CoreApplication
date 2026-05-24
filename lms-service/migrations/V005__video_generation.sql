-- Create video_generation_jobs table
CREATE TABLE IF NOT EXISTS video_generation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type VARCHAR(50) NOT NULL CHECK (target_type IN ('course', 'section')),
    target_id BIGINT NOT NULL,
    custom_prompt TEXT,
    language VARCHAR(20) NOT NULL DEFAULT 'vi',
    template_type VARCHAR(20) NOT NULL DEFAULT 'dark' CHECK (template_type IN ('dark', 'light')),

    -- Identity & Authorization
    created_by BIGINT NOT NULL REFERENCES users(id),

    -- Status Tracking
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','PLANNING','SCRIPTING','RENDERING','UPLOADING',
                          'COMPLETED','PUBLISHING','PUBLIC','FAILED','CANCELLED')),
    progress INT NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),

    -- Error Handling & Reliability
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    last_error_message TEXT,
    last_error_at TIMESTAMPTZ,

    -- YouTube Metadata
    youtube_video_id VARCHAR(100),
    youtube_url TEXT,
    visibility VARCHAR(20) NOT NULL DEFAULT 'unlisted'
        CHECK (visibility IN ('unlisted', 'public')),

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_video_jobs_target ON video_generation_jobs(target_type, target_id);
CREATE INDEX idx_video_jobs_user_status ON video_generation_jobs(created_by, status);
CREATE INDEX idx_video_jobs_user_date ON video_generation_jobs(created_by, created_at);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_video_jobs_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER video_jobs_updated_at
    BEFORE UPDATE ON video_generation_jobs
    FOR EACH ROW EXECUTE FUNCTION update_video_jobs_timestamp();
