CREATE TABLE IF NOT EXISTS lab_runtime_tasks (
    id BIGSERIAL PRIMARY KEY,
    lab_id BIGINT NOT NULL REFERENCES labs(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    runtime_type VARCHAR(20) NOT NULL CHECK (runtime_type IN ('WORKSPACE','HPC')),
    verifier_type VARCHAR(30) NOT NULL CHECK (verifier_type IN (
        'FILE_EXISTS','FILE_CONTAINS','COMMAND_EXIT','COMMAND_OUTPUT',
        'HPC_JOB_SUBMITTED','HPC_JOB_COMPLETED'
    )),
    verifier_config JSONB NOT NULL DEFAULT '{}',
    weight INT NOT NULL DEFAULT 1 CHECK (weight > 0 AND weight <= 1000),
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    order_index INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_runtime_tasks_lab ON lab_runtime_tasks(lab_id, order_index, id);

CREATE TABLE IF NOT EXISTS lab_runtime_task_attempts (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES lab_runtime_tasks(id) ON DELETE CASCADE,
    lab_id BIGINT NOT NULL REFERENCES labs(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id),
    session_id VARCHAR(100),
    passed BOOLEAN NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    evidence JSONB NOT NULL DEFAULT '{}',
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_runtime_task_attempts_user ON lab_runtime_task_attempts(lab_id, user_id, checked_at DESC);
