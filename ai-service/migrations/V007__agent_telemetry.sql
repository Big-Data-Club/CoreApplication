-- migrations/V007__agent_telemetry.sql
-- Create table to log multi-agent telemetry traces for model training/tuning.

CREATE TABLE IF NOT EXISTS agent_telemetry_logs (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    turn_id VARCHAR(16) NOT NULL,
    user_query TEXT NOT NULL,
    spawning_score NUMERIC(5, 4) NOT NULL,
    spawning_breakdown JSONB NOT NULL,
    consolidation JSONB,
    sub_agent_runs JSONB NOT NULL,
    critique_report JSONB,
    final_answer TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_telemetry_session_id ON agent_telemetry_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_telemetry_created_at ON agent_telemetry_logs(created_at);
