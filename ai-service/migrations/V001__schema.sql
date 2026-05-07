CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================
-- KNOWLEDGE NODES
-- Embeddings stored in Qdrant (USE_QDRANT=true).
-- description_embedding column nullable — pgvector fallback only.
-- =============================================================

CREATE TABLE IF NOT EXISTS knowledge_nodes (
    id                    BIGSERIAL PRIMARY KEY,
    course_id             BIGINT NOT NULL,
    parent_id             BIGINT REFERENCES knowledge_nodes(id) ON DELETE SET NULL,
    name                  VARCHAR(255) NOT NULL,
    name_vi               VARCHAR(255),
    name_en               VARCHAR(255),
    description           TEXT,
    level                 INTEGER DEFAULT 0,
    order_index           INTEGER DEFAULT 0,
    source_content_id     BIGINT,
    source_content_title  TEXT DEFAULT '',
    auto_generated        BOOLEAN DEFAULT false,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 'tr_kn_updated'
                     AND tgrelid = 'knowledge_nodes'::regclass) THEN
        CREATE TRIGGER tr_kn_updated
            BEFORE UPDATE ON knowledge_nodes
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- =============================================================
-- KNOWLEDGE NODE RELATIONS
-- =============================================================

CREATE TABLE IF NOT EXISTS knowledge_node_relations (
    id             BIGSERIAL PRIMARY KEY,
    course_id      BIGINT NOT NULL,
    source_node_id BIGINT NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    target_node_id BIGINT NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    relation_type  VARCHAR(30) DEFAULT 'related'
                       CHECK (relation_type IN ('prerequisite', 'related', 'extends')),
    strength       FLOAT DEFAULT 1.0 CHECK (strength BETWEEN 0.0 AND 1.0),
    auto_generated BOOLEAN DEFAULT true,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_node_id, target_node_id, relation_type)
);

-- =============================================================
-- DOCUMENT CHUNKS
-- =============================================================

CREATE TABLE IF NOT EXISTS document_chunks (
    id              BIGSERIAL PRIMARY KEY,
    node_id         BIGINT REFERENCES knowledge_nodes(id) ON DELETE SET NULL,
    content_id      BIGINT,
    course_id       BIGINT NOT NULL,
    chunk_text      TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    chunk_hash      VARCHAR(64) UNIQUE,
    embedding_model VARCHAR(64) DEFAULT 'bge-m3',
    source_type     VARCHAR(20) DEFAULT 'document'
                        CHECK (source_type IN ('document', 'video')),
    page_number     INTEGER,
    start_time_sec  INTEGER,
    end_time_sec    INTEGER,
    language        VARCHAR(10) DEFAULT 'vi',
    status          VARCHAR(20) DEFAULT 'ready'
                        CHECK (status IN ('pending', 'processing', 'ready', 'error')),
    parent_chunk_id BIGINT REFERENCES document_chunks(id) ON DELETE CASCADE,
    chunk_level     VARCHAR(10) DEFAULT 'child' CHECK (chunk_level IN ('parent', 'child')),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================
-- AI DIAGNOSES
-- =============================================================

CREATE TABLE IF NOT EXISTS ai_diagnoses (
    id                 BIGSERIAL PRIMARY KEY,
    student_id         BIGINT NOT NULL,
    attempt_id         BIGINT,
    question_id        BIGINT,
    node_id            BIGINT REFERENCES knowledge_nodes(id) ON DELETE SET NULL,
    wrong_answer       TEXT,
    correct_answer     TEXT,
    explanation        TEXT NOT NULL,
    gap_type           VARCHAR(50),
    knowledge_gap      TEXT,
    study_suggestion   TEXT,
    suggested_docs_json JSONB,
    confidence         FLOAT DEFAULT 0.8,
    source_chunk_id    BIGINT REFERENCES document_chunks(id) ON DELETE SET NULL,
    language           VARCHAR(10) DEFAULT 'vi',
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================
-- CONTENT INDEX STATUS
-- =============================================================

CREATE TABLE IF NOT EXISTS content_index_status (
    content_id  BIGINT PRIMARY KEY,
    course_id   BIGINT NOT NULL,
    title       TEXT DEFAULT '',
    status      VARCHAR(20) NOT NULL DEFAULT 'pending',
    error       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- STUDENT KNOWLEDGE PROGRESS
-- =============================================================

CREATE TABLE IF NOT EXISTS student_knowledge_progress (
    id             BIGSERIAL PRIMARY KEY,
    student_id     BIGINT NOT NULL,
    node_id        BIGINT NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    course_id      BIGINT NOT NULL,
    total_attempts INTEGER DEFAULT 0,
    correct_count  INTEGER DEFAULT 0,
    wrong_count    INTEGER DEFAULT 0,
    mastery_level  FLOAT DEFAULT 0.0,
    last_tested_at TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, node_id)
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 'tr_skp_updated'
                     AND tgrelid = 'student_knowledge_progress'::regclass) THEN
        CREATE TRIGGER tr_skp_updated
            BEFORE UPDATE ON student_knowledge_progress
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- =============================================================
-- SPACED REPETITIONS (SM-2)
-- =============================================================

CREATE TABLE IF NOT EXISTS spaced_repetitions (
    id               BIGSERIAL PRIMARY KEY,
    student_id       BIGINT NOT NULL,
    question_id      BIGINT,
    node_id          BIGINT REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    course_id        BIGINT NOT NULL,
    easiness_factor  FLOAT   DEFAULT 2.5,
    interval_days    INTEGER DEFAULT 1,
    repetitions      INTEGER DEFAULT 0,
    quality_last     INTEGER DEFAULT 0,
    next_review_date DATE NOT NULL DEFAULT CURRENT_DATE,
    last_reviewed_at TIMESTAMP,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, question_id)
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 'tr_sr_updated'
                     AND tgrelid = 'spaced_repetitions'::regclass) THEN
        CREATE TRIGGER tr_sr_updated
            BEFORE UPDATE ON spaced_repetitions
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- =============================================================
-- AI QUIZ GENERATIONS
-- =============================================================

CREATE TABLE IF NOT EXISTS ai_quiz_generations (
    id               BIGSERIAL PRIMARY KEY,
    node_id          BIGINT REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    course_id        BIGINT NOT NULL,
    created_by       BIGINT NOT NULL,
    bloom_level      VARCHAR(20)
                         CHECK (bloom_level IN
                             ('remember','understand','apply','analyze','evaluate','create')),
    question_text    TEXT NOT NULL,
    question_type    VARCHAR(50) NOT NULL,
    answer_options   JSONB,
    correct_answer   TEXT,
    explanation      TEXT,
    source_quote     TEXT,
    source_chunk_id  BIGINT REFERENCES document_chunks(id) ON DELETE SET NULL,
    language         VARCHAR(10) DEFAULT 'vi',
    status           VARCHAR(20) DEFAULT 'DRAFT'
                         CHECK (status IN ('DRAFT','APPROVED','REJECTED','PUBLISHED')),
    review_note      TEXT,
    reviewed_by      BIGINT,
    reviewed_at      TIMESTAMP,
    quiz_question_id BIGINT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 'tr_aiqg_updated'
                     AND tgrelid = 'ai_quiz_generations'::regclass) THEN
        CREATE TRIGGER tr_aiqg_updated
            BEFORE UPDATE ON ai_quiz_generations
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- =============================================================
-- FLASHCARDS
-- =============================================================

CREATE TABLE IF NOT EXISTS flashcards (
    id                  BIGSERIAL PRIMARY KEY,
    course_id           BIGINT NOT NULL,
    node_id             BIGINT REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    lesson_id           BIGINT,
    content_id          BIGINT,
    student_id          BIGINT NOT NULL,
    front_text          TEXT NOT NULL,
    back_text           TEXT NOT NULL,
    source_diagnosis_id BIGINT REFERENCES ai_diagnoses(id) ON DELETE SET NULL,
    status              VARCHAR(20) DEFAULT 'ACTIVE'
                            CHECK (status IN ('ACTIVE', 'INACTIVE', 'ARCHIVED')),
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 'tr_fc_updated'
                     AND tgrelid = 'flashcards'::regclass) THEN
        CREATE TRIGGER tr_fc_updated
            BEFORE UPDATE ON flashcards
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- =============================================================
-- FLASHCARD REPETITIONS
-- =============================================================

CREATE TABLE IF NOT EXISTS flashcard_repetitions (
    id               BIGSERIAL PRIMARY KEY,
    student_id       BIGINT NOT NULL,
    flashcard_id     BIGINT NOT NULL REFERENCES flashcards(id) ON DELETE CASCADE,
    course_id        BIGINT NOT NULL,
    easiness_factor  FLOAT   DEFAULT 2.5,
    interval_days    INTEGER DEFAULT 1,
    repetitions      INTEGER DEFAULT 0,
    quality_last     INTEGER DEFAULT 0,
    next_review_date DATE NOT NULL DEFAULT CURRENT_DATE,
    last_reviewed_at TIMESTAMP,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, flashcard_id)
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 'tr_fcr_updated'
                     AND tgrelid = 'flashcard_repetitions'::regclass) THEN
        CREATE TRIGGER tr_fcr_updated
            BEFORE UPDATE ON flashcard_repetitions
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- =============================================================
-- EMBEDDING REINDEX JOBS
-- =============================================================

CREATE TABLE IF NOT EXISTS embedding_reindex_jobs (
    id            BIGSERIAL PRIMARY KEY,
    course_id     BIGINT,
    content_id    BIGINT,
    status        VARCHAR(20) DEFAULT 'pending'
                      CHECK (status IN ('pending', 'processing', 'done', 'failed')),
    chunks_total  INTEGER DEFAULT 0,
    chunks_done   INTEGER DEFAULT 0,
    error_message TEXT,
    started_at    TIMESTAMP,
    completed_at  TIMESTAMP,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 'tr_erj_updated'
                     AND tgrelid = 'embedding_reindex_jobs'::regclass) THEN
        CREATE TRIGGER tr_erj_updated
            BEFORE UPDATE ON embedding_reindex_jobs
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- =============================================================
-- VIEWS
-- =============================================================

CREATE OR REPLACE VIEW v_reindex_progress AS
SELECT
    COUNT(*)                                          AS total_jobs,
    COUNT(*) FILTER (WHERE status = 'done')           AS done,
    COUNT(*) FILTER (WHERE status = 'pending')        AS pending,
    COUNT(*) FILTER (WHERE status = 'processing')     AS processing,
    COUNT(*) FILTER (WHERE status = 'failed')         AS failed,
    ROUND(
        COUNT(*) FILTER (WHERE status = 'done')::NUMERIC
        / NULLIF(COUNT(*), 0) * 100, 1
    )                                                 AS pct_done,
    SUM(chunks_total)                                 AS total_chunks,
    SUM(chunks_done)                                  AS reindexed_chunks
FROM embedding_reindex_jobs;

CREATE OR REPLACE VIEW knowledge_graph_view AS
SELECT
    kn.id                           AS node_id,
    kn.course_id,
    kn.name,
    kn.name_vi,
    kn.level,
    kn.auto_generated,
    kn.source_content_id,
    COUNT(DISTINCT dc.id)           AS chunk_count,
    COUNT(DISTINCT knr_out.id)      AS out_edges,
    COUNT(DISTINCT knr_in.id)       AS in_edges
FROM       knowledge_nodes          kn
LEFT JOIN  document_chunks          dc      ON  dc.node_id        = kn.id
LEFT JOIN  knowledge_node_relations knr_out ON  knr_out.source_node_id = kn.id
LEFT JOIN  knowledge_node_relations knr_in  ON  knr_in.target_node_id  = kn.id
GROUP BY
    kn.id, kn.course_id, kn.name, kn.name_vi,
    kn.level, kn.auto_generated, kn.source_content_id;

-- =============================================================
-- AGENT MEMORY TABLES
-- =============================================================

CREATE TABLE IF NOT EXISTS agent_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         BIGINT NOT NULL,
    agent_type      VARCHAR(20) NOT NULL
                        CHECK (agent_type IN ('teacher', 'mentor')),
    course_id       BIGINT,
    title           VARCHAR(200),
    compressed_ctx  JSONB NOT NULL DEFAULT '{}',
    turn_count      INTEGER DEFAULT 0,
    last_active_at  TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_episodes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES agent_sessions(id) ON DELETE CASCADE,
    user_id         BIGINT NOT NULL,
    agent_type      VARCHAR(20) NOT NULL
                        CHECK (agent_type IN ('teacher', 'mentor')),
    summary         TEXT NOT NULL,
    qdrant_point_id BIGINT,
    course_id       BIGINT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_messages (
    id          BIGSERIAL PRIMARY KEY,
    session_id  UUID NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    role        VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content     TEXT NOT NULL DEFAULT '',
    metadata    JSONB DEFAULT '{}',    -- toolActivities, uiComponent, hitlRequest, etc.
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- LLM PROVIDERS, MODELS, KEYS, AND LOGS
-- =============================================================

CREATE TABLE IF NOT EXISTS llm_providers (
    id             BIGSERIAL PRIMARY KEY,
    code           VARCHAR(40)  NOT NULL UNIQUE,      
    display_name   VARCHAR(120) NOT NULL,
    adapter_type   VARCHAR(40)  NOT NULL,             
    base_url       VARCHAR(255),                      
    enabled        BOOLEAN      NOT NULL DEFAULT TRUE,
    config         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
 
CREATE TABLE IF NOT EXISTS llm_api_keys (
    id                      BIGSERIAL PRIMARY KEY,
    provider_id             BIGINT      NOT NULL REFERENCES llm_providers(id) ON DELETE CASCADE,
    alias                   VARCHAR(80) NOT NULL,                 
    encrypted_key           TEXT        NOT NULL,                 
    key_fingerprint         VARCHAR(32) NOT NULL,                 
    status                  VARCHAR(20) NOT NULL DEFAULT 'active'
                             CHECK (status IN ('active','cooldown','disabled','invalid')),
    rpm_limit               INTEGER,                              
    tpm_limit               INTEGER,                              
    daily_token_limit       BIGINT,                               
    used_today_requests     BIGINT      NOT NULL DEFAULT 0,
    used_today_tokens       BIGINT      NOT NULL DEFAULT 0,
    used_window_start       TIMESTAMPTZ NOT NULL DEFAULT NOW(),   
    cooldown_until          TIMESTAMPTZ,                          
    consecutive_failures    INTEGER     NOT NULL DEFAULT 0,
    last_error              TEXT,
    last_used_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_id, alias)
);
 
CREATE TABLE IF NOT EXISTS llm_models (
    id                  BIGSERIAL PRIMARY KEY,
    provider_id         BIGINT       NOT NULL REFERENCES llm_providers(id) ON DELETE CASCADE,
    model_name          VARCHAR(120) NOT NULL,     
    display_name        VARCHAR(160),
    family              VARCHAR(40),               
    context_window      INTEGER      NOT NULL DEFAULT 8192,
    supports_json       BOOLEAN      NOT NULL DEFAULT TRUE,
    supports_tools      BOOLEAN      NOT NULL DEFAULT FALSE,
    supports_streaming  BOOLEAN      NOT NULL DEFAULT TRUE,
    supports_vision     BOOLEAN      NOT NULL DEFAULT FALSE,
    input_cost_per_1k   NUMERIC(10,6) NOT NULL DEFAULT 0,
    output_cost_per_1k  NUMERIC(10,6) NOT NULL DEFAULT 0,
    default_temperature NUMERIC(4,3) NOT NULL DEFAULT 0.3,
    default_max_tokens  INTEGER      NOT NULL DEFAULT 1024,
    enabled             BOOLEAN      NOT NULL DEFAULT TRUE,
    config              JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (provider_id, model_name)
);
 
CREATE TABLE IF NOT EXISTS task_model_bindings (
    id                  BIGSERIAL PRIMARY KEY,
    task_code           VARCHAR(80)  NOT NULL,      
    model_id            BIGINT       NOT NULL REFERENCES llm_models(id) ON DELETE CASCADE,
    priority            INTEGER      NOT NULL DEFAULT 100,   
    temperature         NUMERIC(4,3),                       
    max_tokens          INTEGER,                             
    json_mode           BOOLEAN      NOT NULL DEFAULT FALSE,
    pinned              BOOLEAN      NOT NULL DEFAULT FALSE, 
    enabled             BOOLEAN      NOT NULL DEFAULT TRUE,
    notes               TEXT,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (task_code, model_id)
);
 
CREATE TABLE IF NOT EXISTS llm_usage_log (
    id                BIGSERIAL PRIMARY KEY,
    task_code         VARCHAR(80)  NOT NULL,
    model_id          BIGINT       REFERENCES llm_models(id) ON DELETE SET NULL,
    api_key_id        BIGINT       REFERENCES llm_api_keys(id) ON DELETE SET NULL,
    provider_code     VARCHAR(40),                          
    model_name        VARCHAR(120),                         
    prompt_tokens     INTEGER      NOT NULL DEFAULT 0,
    completion_tokens INTEGER      NOT NULL DEFAULT 0,
    total_tokens      INTEGER      NOT NULL DEFAULT 0,
    latency_ms        INTEGER      NOT NULL DEFAULT 0,
    success           BOOLEAN      NOT NULL,
    fallback_used     BOOLEAN      NOT NULL DEFAULT FALSE,  
    attempt_no        INTEGER      NOT NULL DEFAULT 1,
    error_code        VARCHAR(60),
    error_message     TEXT,
    request_id        VARCHAR(120),                         
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
 
CREATE OR REPLACE FUNCTION trg_llm_touch_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
 
DROP TRIGGER IF EXISTS trg_llm_providers_updated  ON llm_providers;
DROP TRIGGER IF EXISTS trg_llm_api_keys_updated   ON llm_api_keys;
DROP TRIGGER IF EXISTS trg_llm_models_updated     ON llm_models;
DROP TRIGGER IF EXISTS trg_task_bindings_updated  ON task_model_bindings;
 
CREATE TRIGGER trg_llm_providers_updated  BEFORE UPDATE ON llm_providers
    FOR EACH ROW EXECUTE FUNCTION trg_llm_touch_updated_at();
CREATE TRIGGER trg_llm_api_keys_updated   BEFORE UPDATE ON llm_api_keys
    FOR EACH ROW EXECUTE FUNCTION trg_llm_touch_updated_at();
CREATE TRIGGER trg_llm_models_updated     BEFORE UPDATE ON llm_models
    FOR EACH ROW EXECUTE FUNCTION trg_llm_touch_updated_at();
CREATE TRIGGER trg_task_bindings_updated  BEFORE UPDATE ON task_model_bindings
    FOR EACH ROW EXECUTE FUNCTION trg_llm_touch_updated_at();

-- =============================================================
-- GRAPH CONSOLIDATION LOG
-- =============================================================

CREATE TABLE IF NOT EXISTS graph_consolidation_log (
    id              BIGSERIAL PRIMARY KEY,
    course_id       BIGINT NOT NULL,
    survivor_id     BIGINT NOT NULL,
    absorbed_ids    BIGINT[] NOT NULL,
    old_names       JSONB,
    new_name        TEXT,
    new_description TEXT,
    chunks_moved    INTEGER DEFAULT 0,
    triggered_by    BIGINT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
