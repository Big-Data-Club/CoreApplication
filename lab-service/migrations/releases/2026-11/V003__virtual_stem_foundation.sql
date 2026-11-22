-- Virtual STEM Lab foundation: immutable definitions, learner runs, trials and evidence.
-- Forward recovery: disable the new API routes, preserve the append-only evidence,
-- and supersede affected lab versions. Do not down-migrate by deleting learner data.

ALTER TABLE labs DROP CONSTRAINT IF EXISTS labs_lab_type_check;
ALTER TABLE labs ADD CONSTRAINT labs_lab_type_check CHECK (lab_type IN (
    'CODING', 'HPC', 'JUPYTER', 'WORKSPACE', 'DATABASE', 'CUSTOM',
    'PLANT', 'ROBOT'
));

CREATE TABLE IF NOT EXISTS lab_versions (
    id                  BIGSERIAL PRIMARY KEY,
    lab_id              BIGINT NOT NULL REFERENCES labs(id) ON DELETE CASCADE,
    version_number      INT NOT NULL CHECK (version_number > 0),
    status              VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
                        CHECK (status IN ('DRAFT', 'VALIDATED', 'PUBLISHED', 'SUPERSEDED')),
    definition_hash     VARCHAR(64) NOT NULL,
    definition_snapshot JSONB NOT NULL,
    created_by          BIGINT NOT NULL REFERENCES users(id),
    validated_at        TIMESTAMPTZ,
    published_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (lab_id, version_number)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_lab_versions_one_published
    ON lab_versions(lab_id) WHERE status = 'PUBLISHED';
CREATE INDEX IF NOT EXISTS idx_lab_versions_lab
    ON lab_versions(lab_id, version_number DESC);

CREATE TABLE IF NOT EXISTS experiment_definitions (
    lab_version_id         BIGINT PRIMARY KEY REFERENCES lab_versions(id) ON DELETE CASCADE,
    domain                 VARCHAR(20) NOT NULL CHECK (domain IN ('PLANT', 'ROBOT')),
    inquiry_level          VARCHAR(30) NOT NULL
                           CHECK (inquiry_level IN ('STRUCTURED', 'GUIDED', 'OPEN_INQUIRY')),
    workflow_schema_version INT NOT NULL DEFAULT 1 CHECK (workflow_schema_version > 0),
    model_version          VARCHAR(100) NOT NULL,
    learning_objectives    JSONB NOT NULL DEFAULT '[]',
    config                 JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS workflow_nodes (
    lab_version_id   BIGINT NOT NULL REFERENCES lab_versions(id) ON DELETE CASCADE,
    node_key         VARCHAR(100) NOT NULL,
    node_type        VARCHAR(40) NOT NULL CHECK (node_type IN (
                     'INSTRUCTION', 'QUESTION', 'PREDICTION', 'CONFIGURE', 'BUILD',
                     'RUN', 'MEASURE', 'CHECKPOINT', 'ANALYZE', 'EXPLAIN',
                     'ITERATE', 'REFLECT'
                     )),
    title            VARCHAR(255) NOT NULL,
    config           JSONB NOT NULL DEFAULT '{}',
    required_evidence JSONB NOT NULL DEFAULT '[]',
    order_hint       INT NOT NULL DEFAULT 0 CHECK (order_hint >= 0),
    PRIMARY KEY (lab_version_id, node_key)
);

CREATE TABLE IF NOT EXISTS workflow_edges (
    id                   BIGSERIAL PRIMARY KEY,
    lab_version_id       BIGINT NOT NULL REFERENCES lab_versions(id) ON DELETE CASCADE,
    from_node_key        VARCHAR(100) NOT NULL,
    to_node_key          VARCHAR(100) NOT NULL,
    condition_expression TEXT NOT NULL DEFAULT 'always',
    priority             INT NOT NULL DEFAULT 0,
    FOREIGN KEY (lab_version_id, from_node_key)
        REFERENCES workflow_nodes(lab_version_id, node_key) ON DELETE CASCADE,
    FOREIGN KEY (lab_version_id, to_node_key)
        REFERENCES workflow_nodes(lab_version_id, node_key) ON DELETE CASCADE,
    UNIQUE (lab_version_id, from_node_key, to_node_key, priority)
);

CREATE TABLE IF NOT EXISTS experiment_variables (
    lab_version_id BIGINT NOT NULL REFERENCES lab_versions(id) ON DELETE CASCADE,
    variable_key   VARCHAR(100) NOT NULL,
    display_name   VARCHAR(255) NOT NULL,
    variable_role  VARCHAR(20) NOT NULL
                   CHECK (variable_role IN ('INDEPENDENT', 'DEPENDENT', 'CONTROLLED')),
    data_type      VARCHAR(20) NOT NULL
                   CHECK (data_type IN ('NUMBER', 'INTEGER', 'BOOLEAN', 'STRING')),
    unit           VARCHAR(50) NOT NULL DEFAULT '',
    min_value      DOUBLE PRECISION,
    max_value      DOUBLE PRECISION,
    default_value  JSONB,
    source_id      VARCHAR(255) NOT NULL DEFAULT '',
    PRIMARY KEY (lab_version_id, variable_key),
    CHECK (min_value IS NULL OR max_value IS NULL OR min_value <= max_value)
);

CREATE TABLE IF NOT EXISTS lab_runs (
    id                 BIGSERIAL PRIMARY KEY,
    lab_version_id     BIGINT NOT NULL REFERENCES lab_versions(id),
    user_id            BIGINT NOT NULL REFERENCES users(id),
    idempotency_key    VARCHAR(128) NOT NULL,
    status             VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
                       CHECK (status IN ('ACTIVE', 'COMPLETED', 'ABANDONED')),
    current_node_key   VARCHAR(100),
    last_event_seq     BIGINT NOT NULL DEFAULT 0,
    started_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at           TIMESTAMPTZ,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (lab_version_id, user_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_lab_runs_version_user
    ON lab_runs(lab_version_id, user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_lab_runs_active
    ON lab_runs(lab_version_id, status) WHERE status = 'ACTIVE';

CREATE TABLE IF NOT EXISTS experiment_trials (
    id              BIGSERIAL PRIMARY KEY,
    run_id          BIGINT NOT NULL REFERENCES lab_runs(id) ON DELETE CASCADE,
    trial_number    INT NOT NULL CHECK (trial_number > 0),
    seed            BIGINT NOT NULL CHECK (seed >= 0),
    model_version   VARCHAR(100) NOT NULL,
    config_snapshot JSONB NOT NULL DEFAULT '{}',
    status          VARCHAR(20) NOT NULL DEFAULT 'READY'
                    CHECK (status IN ('READY', 'RUNNING', 'PAUSED', 'COMPLETED', 'FAILED', 'CANCELLED')),
    started_at      TIMESTAMPTZ,
    ended_at        TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, trial_number),
    UNIQUE (id, run_id)
);

CREATE INDEX IF NOT EXISTS idx_experiment_trials_run
    ON experiment_trials(run_id, trial_number);

CREATE TABLE IF NOT EXISTS evidence_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_event_id UUID NOT NULL,
    schema_version  INT NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    run_id          BIGINT NOT NULL REFERENCES lab_runs(id) ON DELETE CASCADE,
    trial_id        BIGINT,
    seq_no          BIGINT NOT NULL CHECK (seq_no > 0),
    actor_id        BIGINT NOT NULL REFERENCES users(id),
    actor_type      VARCHAR(20) NOT NULL CHECK (actor_type IN ('LEARNER', 'TEACHER', 'SYSTEM')),
    verb            VARCHAR(60) NOT NULL,
    object_data     JSONB NOT NULL,
    result_data     JSONB NOT NULL DEFAULT '{}',
    context_data    JSONB NOT NULL DEFAULT '{}',
    sim_time_ms     BIGINT CHECK (sim_time_ms IS NULL OR sim_time_ms >= 0),
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (trial_id, run_id)
        REFERENCES experiment_trials(id, run_id),
    UNIQUE (run_id, seq_no),
    UNIQUE (run_id, client_event_id)
);

CREATE INDEX IF NOT EXISTS idx_evidence_events_replay
    ON evidence_events(run_id, seq_no);
CREATE INDEX IF NOT EXISTS idx_evidence_events_trial
    ON evidence_events(trial_id, seq_no) WHERE trial_id IS NOT NULL;
