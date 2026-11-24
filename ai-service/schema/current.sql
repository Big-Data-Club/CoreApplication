-- Consolidated schema reconstructed from repository SQL, not a Neon dump.
-- NEW databases only. Existing deployments continue using migration history.
-- Tables contain their final columns; indexes, constraints and seed defaults follow.
-- See README.md for scope and regeneration.

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;



COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';



CREATE FUNCTION public.trg_llm_touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;



CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;


CREATE TABLE public.agent_episodes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    session_id uuid,
    user_id bigint NOT NULL,
    agent_type character varying(20) NOT NULL,
    summary text NOT NULL,
    qdrant_point_id bigint,
    course_id bigint,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT agent_episodes_agent_type_check CHECK (((agent_type)::text = ANY (ARRAY[('teacher'::character varying)::text, ('mentor'::character varying)::text])))
);



CREATE TABLE public.agent_message_feedback (
    id bigint NOT NULL,
    message_id bigint NOT NULL,
    session_id uuid NOT NULL,
    user_id bigint NOT NULL,
    rating character varying(10) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agent_message_feedback_rating_check CHECK (((rating)::text = ANY (ARRAY[('like'::character varying)::text, ('dislike'::character varying)::text])))
);



CREATE SEQUENCE public.agent_message_feedback_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.agent_message_feedback_id_seq OWNED BY public.agent_message_feedback.id;



CREATE TABLE public.agent_messages (
    id bigint NOT NULL,
    session_id uuid NOT NULL,
    role character varying(20) NOT NULL,
    content text DEFAULT ''::text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT agent_messages_role_check CHECK (((role)::text = ANY (ARRAY[('user'::character varying)::text, ('assistant'::character varying)::text, ('system'::character varying)::text, ('tool'::character varying)::text])))
);



CREATE SEQUENCE public.agent_messages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.agent_messages_id_seq OWNED BY public.agent_messages.id;



CREATE TABLE public.agent_sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id bigint NOT NULL,
    agent_type character varying(20) NOT NULL,
    course_id bigint,
    title character varying(200),
    compressed_ctx jsonb DEFAULT '{}'::jsonb NOT NULL,
    turn_count integer DEFAULT 0,
    last_active_at timestamp with time zone DEFAULT now(),
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT agent_sessions_agent_type_check CHECK (((agent_type)::text = ANY (ARRAY[('teacher'::character varying)::text, ('mentor'::character varying)::text])))
);



CREATE TABLE public.agent_telemetry_logs (
    id integer NOT NULL,
    session_id character varying(36) NOT NULL,
    turn_id character varying(16) NOT NULL,
    user_query text NOT NULL,
    spawning_score numeric(5,4) NOT NULL,
    spawning_breakdown jsonb NOT NULL,
    consolidation jsonb,
    sub_agent_runs jsonb NOT NULL,
    critique_report jsonb,
    final_answer text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.agent_telemetry_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.agent_telemetry_logs_id_seq OWNED BY public.agent_telemetry_logs.id;



CREATE TABLE public.ai_diagnoses (
    id bigint NOT NULL,
    student_id bigint NOT NULL,
    attempt_id bigint,
    question_id bigint,
    node_id bigint,
    wrong_answer text,
    correct_answer text,
    explanation text NOT NULL,
    gap_type character varying(50),
    knowledge_gap text,
    study_suggestion text,
    suggested_docs_json jsonb,
    confidence double precision DEFAULT 0.8,
    source_chunk_id bigint,
    language character varying(10) DEFAULT 'vi'::character varying,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.ai_diagnoses_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.ai_diagnoses_id_seq OWNED BY public.ai_diagnoses.id;



CREATE TABLE public.ai_quiz_generations (
    id bigint NOT NULL,
    node_id bigint,
    course_id bigint NOT NULL,
    created_by bigint NOT NULL,
    bloom_level character varying(20),
    question_text text NOT NULL,
    question_type character varying(50) NOT NULL,
    answer_options jsonb,
    correct_answer text,
    explanation text,
    source_quote text,
    source_chunk_id bigint,
    language character varying(10) DEFAULT 'vi'::character varying,
    status character varying(20) DEFAULT 'DRAFT'::character varying,
    review_note text,
    reviewed_by bigint,
    reviewed_at timestamp without time zone,
    quiz_question_id bigint,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ai_quiz_generations_bloom_level_check CHECK (((bloom_level)::text = ANY (ARRAY[('remember'::character varying)::text, ('understand'::character varying)::text, ('apply'::character varying)::text, ('analyze'::character varying)::text, ('evaluate'::character varying)::text, ('create'::character varying)::text]))),
    CONSTRAINT ai_quiz_generations_status_check CHECK (((status)::text = ANY (ARRAY[('DRAFT'::character varying)::text, ('APPROVED'::character varying)::text, ('REJECTED'::character varying)::text, ('PUBLISHED'::character varying)::text])))
);



CREATE SEQUENCE public.ai_quiz_generations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.ai_quiz_generations_id_seq OWNED BY public.ai_quiz_generations.id;



CREATE TABLE public.document_chunks (
    id bigint NOT NULL,
    node_id bigint,
    content_id bigint,
    course_id bigint NOT NULL,
    chunk_text text NOT NULL,
    chunk_index integer NOT NULL,
    chunk_hash character varying(64),
    embedding_model character varying(64) DEFAULT 'bge-m3'::character varying,
    source_type character varying(20) DEFAULT 'document'::character varying,
    page_number integer,
    start_time_sec integer,
    end_time_sec integer,
    language character varying(10) DEFAULT 'vi'::character varying,
    status character varying(20) DEFAULT 'ready'::character varying,
    parent_chunk_id bigint,
    chunk_level character varying(10) DEFAULT 'child'::character varying,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT document_chunks_chunk_level_check CHECK (((chunk_level)::text = ANY (ARRAY[('parent'::character varying)::text, ('child'::character varying)::text]))),
    CONSTRAINT document_chunks_source_type_check CHECK (((source_type)::text = ANY (ARRAY[('document'::character varying)::text, ('video'::character varying)::text]))),
    CONSTRAINT document_chunks_status_check CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('processing'::character varying)::text, ('ready'::character varying)::text, ('error'::character varying)::text])))
);



CREATE MATERIALIZED VIEW public.concept_chunk_map AS
 SELECT node_id,
    course_id,
    count(*) AS chunk_count,
    max(created_at) AS last_indexed,
    min(created_at) AS first_indexed
   FROM public.document_chunks
  WHERE (((status)::text = 'ready'::text) AND (node_id IS NOT NULL))
  GROUP BY node_id, course_id
  WITH NO DATA;



CREATE TABLE public.content_index_status (
    content_id bigint NOT NULL,
    course_id bigint NOT NULL,
    title text DEFAULT ''::text,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    error text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);



CREATE TABLE public.course_blueprints (
    id uuid NOT NULL,
    owner_id bigint NOT NULL,
    origin character varying(20) DEFAULT 'course_create'::character varying NOT NULL,
    status character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
    source_manifest jsonb NOT NULL,
    governance_manifest jsonb DEFAULT '{}'::jsonb NOT NULL,
    plan jsonb NOT NULL,
    validation_report jsonb DEFAULT '{}'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    applied_course_id bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    error_message text,
    processing_stage character varying(32) DEFAULT 'QUEUED'::character varying NOT NULL,
    progress_pct smallint DEFAULT 0 NOT NULL,
    lease_owner character varying(255),
    lease_until timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    CONSTRAINT course_blueprints_origin_check CHECK (((origin)::text = ANY (ARRAY[('course_create'::character varying)::text, ('chatbot'::character varying)::text]))),
    CONSTRAINT course_blueprints_progress_pct_check CHECK (((progress_pct >= 0) AND (progress_pct <= 100))),
    CONSTRAINT course_blueprints_status_check CHECK (((status)::text = ANY (ARRAY[('PROCESSING'::character varying)::text, ('DRAFT'::character varying)::text, ('APPROVED'::character varying)::text, ('CANCELLED'::character varying)::text, ('APPLIED'::character varying)::text, ('FAILED'::character varying)::text])))
);



CREATE TABLE public.course_material_routing_jobs (
    id uuid NOT NULL,
    owner_id bigint NOT NULL,
    course_id bigint NOT NULL,
    status character varying(20) DEFAULT 'PROCESSING'::character varying NOT NULL,
    documents jsonb NOT NULL,
    sections jsonb NOT NULL,
    suggestions jsonb DEFAULT '[]'::jsonb NOT NULL,
    error_message text,
    lease_owner character varying(255),
    lease_until timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT course_material_routing_jobs_status_check CHECK (((status)::text = ANY (ARRAY[('PROCESSING'::character varying)::text, ('READY'::character varying)::text, ('FAILED'::character varying)::text, ('CANCELLED'::character varying)::text])))
);



CREATE SEQUENCE public.document_chunks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.document_chunks_id_seq OWNED BY public.document_chunks.id;



CREATE TABLE public.embedding_reindex_jobs (
    id bigint NOT NULL,
    course_id bigint,
    content_id bigint,
    status character varying(20) DEFAULT 'pending'::character varying,
    chunks_total integer DEFAULT 0,
    chunks_done integer DEFAULT 0,
    error_message text,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT embedding_reindex_jobs_status_check CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('processing'::character varying)::text, ('done'::character varying)::text, ('failed'::character varying)::text])))
);



CREATE SEQUENCE public.embedding_reindex_jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.embedding_reindex_jobs_id_seq OWNED BY public.embedding_reindex_jobs.id;



CREATE TABLE public.flashcard_repetitions (
    id bigint NOT NULL,
    student_id bigint NOT NULL,
    flashcard_id bigint NOT NULL,
    course_id bigint NOT NULL,
    easiness_factor double precision DEFAULT 2.5,
    interval_days integer DEFAULT 1,
    repetitions integer DEFAULT 0,
    quality_last integer DEFAULT 0,
    next_review_date date DEFAULT CURRENT_DATE NOT NULL,
    last_reviewed_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.flashcard_repetitions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.flashcard_repetitions_id_seq OWNED BY public.flashcard_repetitions.id;



CREATE TABLE public.flashcards (
    id bigint NOT NULL,
    course_id bigint NOT NULL,
    node_id bigint,
    lesson_id bigint,
    content_id bigint,
    student_id bigint NOT NULL,
    front_text text NOT NULL,
    back_text text NOT NULL,
    source_diagnosis_id bigint,
    status character varying(20) DEFAULT 'ACTIVE'::character varying,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT flashcards_status_check CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('INACTIVE'::character varying)::text, ('ARCHIVED'::character varying)::text])))
);



CREATE SEQUENCE public.flashcards_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.flashcards_id_seq OWNED BY public.flashcards.id;



CREATE TABLE public.graph_consolidation_log (
    id bigint NOT NULL,
    course_id bigint NOT NULL,
    survivor_id bigint NOT NULL,
    absorbed_ids bigint[] NOT NULL,
    old_names jsonb,
    new_name text,
    new_description text,
    chunks_moved integer DEFAULT 0,
    triggered_by bigint,
    created_at timestamp with time zone DEFAULT now()
);



CREATE SEQUENCE public.graph_consolidation_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.graph_consolidation_log_id_seq OWNED BY public.graph_consolidation_log.id;



CREATE TABLE public.knowledge_node_relations (
    id bigint NOT NULL,
    course_id bigint NOT NULL,
    source_node_id bigint NOT NULL,
    target_node_id bigint NOT NULL,
    relation_type character varying(30) DEFAULT 'related'::character varying,
    strength double precision DEFAULT 1.0,
    auto_generated boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT knowledge_node_relations_relation_type_check CHECK (((relation_type)::text = ANY (ARRAY[('prerequisite'::character varying)::text, ('related'::character varying)::text, ('extends'::character varying)::text, ('equivalent'::character varying)::text, ('contrasts_with'::character varying)::text]))),
    CONSTRAINT knowledge_node_relations_strength_check CHECK (((strength >= (0.0)::double precision) AND (strength <= (1.0)::double precision)))
);



CREATE TABLE public.knowledge_nodes (
    id bigint NOT NULL,
    course_id bigint NOT NULL,
    parent_id bigint,
    name character varying(255) NOT NULL,
    name_vi character varying(255),
    name_en character varying(255),
    description text,
    level integer DEFAULT 0,
    order_index integer DEFAULT 0,
    source_content_id bigint,
    source_content_title text DEFAULT ''::text,
    auto_generated boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    managed_by character varying(32),
    external_key character varying(160),
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);



CREATE VIEW public.knowledge_graph_view AS
 SELECT kn.id AS node_id,
    kn.course_id,
    kn.name,
    kn.name_vi,
    kn.level,
    kn.auto_generated,
    kn.source_content_id,
    count(DISTINCT dc.id) AS chunk_count,
    count(DISTINCT knr_out.id) AS out_edges,
    count(DISTINCT knr_in.id) AS in_edges
   FROM (((public.knowledge_nodes kn
     LEFT JOIN public.document_chunks dc ON ((dc.node_id = kn.id)))
     LEFT JOIN public.knowledge_node_relations knr_out ON ((knr_out.source_node_id = kn.id)))
     LEFT JOIN public.knowledge_node_relations knr_in ON ((knr_in.target_node_id = kn.id)))
  GROUP BY kn.id, kn.course_id, kn.name, kn.name_vi, kn.level, kn.auto_generated, kn.source_content_id;



CREATE SEQUENCE public.knowledge_node_relations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.knowledge_node_relations_id_seq OWNED BY public.knowledge_node_relations.id;



CREATE SEQUENCE public.knowledge_nodes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.knowledge_nodes_id_seq OWNED BY public.knowledge_nodes.id;



CREATE TABLE public.lab_authoring_jobs (
    id uuid NOT NULL,
    owner_id bigint NOT NULL,
    status text DEFAULT 'QUEUED'::text NOT NULL,
    request jsonb NOT NULL,
    proposal jsonb,
    error text,
    lease_token uuid,
    lease_until timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT lab_authoring_jobs_status_check CHECK ((status = ANY (ARRAY['QUEUED'::text, 'RUNNING'::text, 'READY'::text, 'FAILED'::text])))
);



CREATE TABLE public.llm_api_keys (
    id bigint NOT NULL,
    provider_id bigint NOT NULL,
    alias character varying(80) NOT NULL,
    encrypted_key text NOT NULL,
    key_fingerprint character varying(32) NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    rpm_limit integer,
    tpm_limit integer,
    daily_token_limit bigint,
    used_today_requests bigint DEFAULT 0 NOT NULL,
    used_today_tokens bigint DEFAULT 0 NOT NULL,
    used_window_start timestamp with time zone DEFAULT now() NOT NULL,
    cooldown_until timestamp with time zone,
    consecutive_failures integer DEFAULT 0 NOT NULL,
    last_error text,
    last_used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT llm_api_keys_status_check CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('cooldown'::character varying)::text, ('disabled'::character varying)::text, ('invalid'::character varying)::text])))
);



CREATE SEQUENCE public.llm_api_keys_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.llm_api_keys_id_seq OWNED BY public.llm_api_keys.id;



CREATE TABLE public.llm_models (
    id bigint NOT NULL,
    provider_id bigint NOT NULL,
    model_name character varying(120) NOT NULL,
    display_name character varying(160),
    family character varying(40),
    context_window integer DEFAULT 8192 NOT NULL,
    supports_json boolean DEFAULT true NOT NULL,
    supports_tools boolean DEFAULT false NOT NULL,
    supports_streaming boolean DEFAULT true NOT NULL,
    supports_vision boolean DEFAULT false NOT NULL,
    input_cost_per_1k numeric(10,6) DEFAULT 0 NOT NULL,
    output_cost_per_1k numeric(10,6) DEFAULT 0 NOT NULL,
    default_temperature numeric(4,3) DEFAULT 0.3 NOT NULL,
    default_max_tokens integer DEFAULT 1024 NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.llm_models_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.llm_models_id_seq OWNED BY public.llm_models.id;



CREATE TABLE public.llm_providers (
    id bigint NOT NULL,
    code character varying(40) NOT NULL,
    display_name character varying(120) NOT NULL,
    adapter_type character varying(40) NOT NULL,
    base_url character varying(255),
    enabled boolean DEFAULT true NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.llm_providers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.llm_providers_id_seq OWNED BY public.llm_providers.id;



CREATE TABLE public.llm_usage_log (
    id bigint NOT NULL,
    task_code character varying(80) NOT NULL,
    model_id bigint,
    api_key_id bigint,
    provider_code character varying(40),
    model_name character varying(120),
    prompt_tokens integer DEFAULT 0 NOT NULL,
    completion_tokens integer DEFAULT 0 NOT NULL,
    total_tokens integer DEFAULT 0 NOT NULL,
    latency_ms integer DEFAULT 0 NOT NULL,
    success boolean NOT NULL,
    fallback_used boolean DEFAULT false NOT NULL,
    attempt_no integer DEFAULT 1 NOT NULL,
    error_code character varying(60),
    error_message text,
    request_id character varying(120),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.llm_usage_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.llm_usage_log_id_seq OWNED BY public.llm_usage_log.id;



CREATE TABLE public.mcp_api_keys (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    name character varying(100) DEFAULT 'MCP Key'::character varying NOT NULL,
    key_hash character(64) NOT NULL,
    key_prefix character varying(20) NOT NULL,
    scopes text[] DEFAULT ARRAY['read'::text] NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone,
    last_used_at timestamp with time zone,
    revoked_at timestamp with time zone,
    CONSTRAINT mcp_api_keys_scopes_valid CHECK (((scopes <@ ARRAY['read'::text, 'write'::text]) OR ((scopes <@ ARRAY['workspace:read'::text, 'workspace:create'::text]) AND ('workspace:read'::text = ANY (scopes)))))
);



CREATE SEQUENCE public.mcp_api_keys_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.mcp_api_keys_id_seq OWNED BY public.mcp_api_keys.id;



CREATE TABLE public.mcp_audit_log (
    id bigint NOT NULL,
    key_id bigint,
    user_id bigint NOT NULL,
    action character varying(160) NOT NULL,
    success boolean NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.mcp_audit_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.mcp_audit_log_id_seq OWNED BY public.mcp_audit_log.id;



CREATE TABLE public.mcp_authoring_requests (
    owner_id bigint NOT NULL,
    request_id uuid NOT NULL,
    operation text NOT NULL,
    input_hash text NOT NULL,
    result jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.personal_flashcard_decks (
    id bigint NOT NULL,
    student_id bigint NOT NULL,
    name character varying(120) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    course_id bigint,
    source_content_id bigint,
    source_lesson_id bigint
);



CREATE SEQUENCE public.personal_flashcard_decks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.personal_flashcard_decks_id_seq OWNED BY public.personal_flashcard_decks.id;



CREATE TABLE public.personal_flashcard_jobs (
    id uuid NOT NULL,
    student_id bigint NOT NULL,
    kind character varying(10) NOT NULL,
    status character varying(12) DEFAULT 'pending'::character varying NOT NULL,
    payload jsonb NOT NULL,
    result jsonb,
    error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    course_id bigint,
    CONSTRAINT personal_flashcard_jobs_kind_check CHECK (((kind)::text = ANY (ARRAY[('generate'::character varying)::text, ('check'::character varying)::text, ('content'::character varying)::text, ('quiz'::character varying)::text])))
);



CREATE TABLE public.personal_flashcard_reviews (
    id uuid NOT NULL,
    student_id bigint NOT NULL,
    card_id bigint NOT NULL,
    result jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.personal_flashcards (
    id bigint NOT NULL,
    student_id bigint NOT NULL,
    deck_id bigint NOT NULL,
    front_text text NOT NULL,
    back_text text NOT NULL,
    accepted_answers jsonb DEFAULT '[]'::jsonb NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    language character varying(35) DEFAULT 'vi-VN'::character varying NOT NULL,
    answer_language character varying(35) DEFAULT 'vi-VN'::character varying NOT NULL,
    match_mode character varying(10) DEFAULT 'exact'::character varying NOT NULL,
    case_sensitive boolean DEFAULT false NOT NULL,
    repetitions integer DEFAULT 0 NOT NULL,
    interval_days integer DEFAULT 0 NOT NULL,
    easiness double precision DEFAULT 2.5 NOT NULL,
    due_at timestamp with time zone DEFAULT now() NOT NULL,
    revision integer DEFAULT 1 NOT NULL,
    legacy_id bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    source_node_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    CONSTRAINT personal_flashcards_match_mode_check CHECK (((match_mode)::text = ANY (ARRAY[('exact'::character varying)::text, ('ai'::character varying)::text])))
);



CREATE SEQUENCE public.personal_flashcards_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.personal_flashcards_id_seq OWNED BY public.personal_flashcards.id;



CREATE TABLE public.quiz_insight_results (
    job_id text NOT NULL,
    result jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.review_delivery_receipts (
    event_id text NOT NULL,
    payload_hash text NOT NULL,
    result jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.spaced_repetitions (
    id bigint NOT NULL,
    student_id bigint NOT NULL,
    question_id bigint,
    node_id bigint,
    course_id bigint NOT NULL,
    easiness_factor double precision DEFAULT 2.5,
    interval_days integer DEFAULT 1,
    repetitions integer DEFAULT 0,
    quality_last integer DEFAULT 0,
    next_review_date date DEFAULT CURRENT_DATE NOT NULL,
    last_reviewed_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.spaced_repetitions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.spaced_repetitions_id_seq OWNED BY public.spaced_repetitions.id;



CREATE TABLE public.speech_jobs (
    id uuid NOT NULL,
    owner_id bigint NOT NULL,
    card_id bigint NOT NULL,
    content_hash text NOT NULL,
    request jsonb NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    object_key text,
    error text,
    lease_token uuid,
    lease_until timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT speech_jobs_status_check CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'ready'::text, 'failed'::text])))
);



CREATE TABLE public.student_facts (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    fact text NOT NULL,
    category character varying(50) NOT NULL,
    course_id bigint,
    qdrant_point_id bigint,
    qdrant_synced boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);



CREATE SEQUENCE public.student_facts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.student_facts_id_seq OWNED BY public.student_facts.id;



CREATE TABLE public.student_knowledge_progress (
    id bigint NOT NULL,
    student_id bigint NOT NULL,
    node_id bigint NOT NULL,
    course_id bigint NOT NULL,
    total_attempts integer DEFAULT 0,
    correct_count integer DEFAULT 0,
    wrong_count integer DEFAULT 0,
    mastery_level double precision DEFAULT 0.0,
    last_tested_at timestamp without time zone,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.student_knowledge_progress_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.student_knowledge_progress_id_seq OWNED BY public.student_knowledge_progress.id;



CREATE TABLE public.studio_jobs (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    owner_id bigint NOT NULL,
    operation text NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    request jsonb DEFAULT '{}'::jsonb NOT NULL,
    checkpoint jsonb DEFAULT '{}'::jsonb NOT NULL,
    lease_token uuid,
    lease_until timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT studio_jobs_operation_check CHECK ((operation = ANY (ARRAY['plan'::text, 'render'::text]))),
    CONSTRAINT studio_jobs_status_check CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'ready'::text, 'failed'::text])))
);



CREATE TABLE public.studio_legacy_media_swept (
    project_id uuid NOT NULL
);



CREATE TABLE public.studio_projects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id bigint NOT NULL,
    created_by bigint NOT NULL,
    kind character varying(20) NOT NULL,
    title character varying(300) NOT NULL,
    status character varying(20) DEFAULT 'collecting'::character varying NOT NULL,
    error_detail text,
    context_pack jsonb DEFAULT '[]'::jsonb NOT NULL,
    plan jsonb,
    settings jsonb DEFAULT '{}'::jsonb NOT NULL,
    artifacts jsonb DEFAULT '[]'::jsonb NOT NULL,
    section_hashes jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    current_job_id uuid,
    CONSTRAINT studio_projects_kind_check CHECK (((kind)::text = ANY (ARRAY[('slides'::character varying)::text, ('document'::character varying)::text, ('report'::character varying)::text, ('video'::character varying)::text]))),
    CONSTRAINT studio_projects_status_check CHECK (((status)::text = ANY (ARRAY[('collecting'::character varying)::text, ('planning'::character varying)::text, ('planned'::character varying)::text, ('generating'::character varying)::text, ('ready'::character varying)::text, ('failed'::character varying)::text])))
);



CREATE TABLE public.studio_shared_youtube_connection (
    singleton boolean DEFAULT true NOT NULL,
    encrypted_connection text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT studio_shared_youtube_connection_singleton_check CHECK (singleton)
);



CREATE TABLE public.studio_temporary_media (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    generation text NOT NULL,
    owner_id bigint NOT NULL,
    course_id bigint NOT NULL,
    object_key text NOT NULL,
    storage_bucket text NOT NULL,
    media_type text NOT NULL,
    size_bytes bigint DEFAULT 0 NOT NULL,
    ready_at timestamp with time zone,
    expires_at timestamp with time zone DEFAULT (now() + '03:00:00'::interval),
    deleted_at timestamp with time zone,
    cleanup_attempts integer DEFAULT 0 NOT NULL,
    cleanup_after timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.studio_youtube_uploads (
    id uuid NOT NULL,
    asset_id uuid NOT NULL,
    owner_id bigint NOT NULL,
    channel_id text NOT NULL,
    title text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    privacy text NOT NULL,
    made_for_kids boolean NOT NULL,
    contains_synthetic_media boolean DEFAULT true NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    encrypted_session text,
    video_id text,
    actual_privacy text,
    processing_status text,
    error text,
    lease_token uuid,
    lease_until timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT studio_youtube_uploads_privacy_check CHECK ((privacy = ANY (ARRAY['private'::text, 'unlisted'::text, 'public'::text]))),
    CONSTRAINT studio_youtube_uploads_status_check CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'ready'::text, 'failed'::text])))
);



CREATE TABLE public.task_model_bindings (
    id bigint NOT NULL,
    task_code character varying(80) NOT NULL,
    model_id bigint NOT NULL,
    priority integer DEFAULT 100 NOT NULL,
    temperature numeric(4,3),
    max_tokens integer,
    json_mode boolean DEFAULT false NOT NULL,
    pinned boolean DEFAULT false NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.task_model_bindings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.task_model_bindings_id_seq OWNED BY public.task_model_bindings.id;



CREATE TABLE public.user_concept_mastery (
    user_id bigint NOT NULL,
    concept_id bigint NOT NULL,
    mastery_level double precision DEFAULT 0.0 NOT NULL,
    struggles boolean DEFAULT false NOT NULL,
    interaction_count integer DEFAULT 0 NOT NULL,
    last_interaction timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);



CREATE VIEW public.v_reindex_progress AS
 SELECT count(*) AS total_jobs,
    count(*) FILTER (WHERE ((status)::text = 'done'::text)) AS done,
    count(*) FILTER (WHERE ((status)::text = 'pending'::text)) AS pending,
    count(*) FILTER (WHERE ((status)::text = 'processing'::text)) AS processing,
    count(*) FILTER (WHERE ((status)::text = 'failed'::text)) AS failed,
    round((((count(*) FILTER (WHERE ((status)::text = 'done'::text)))::numeric / (NULLIF(count(*), 0))::numeric) * (100)::numeric), 1) AS pct_done,
    sum(chunks_total) AS total_chunks,
    sum(chunks_done) AS reindexed_chunks
   FROM public.embedding_reindex_jobs;



ALTER TABLE ONLY public.agent_message_feedback ALTER COLUMN id SET DEFAULT nextval('public.agent_message_feedback_id_seq'::regclass);



ALTER TABLE ONLY public.agent_messages ALTER COLUMN id SET DEFAULT nextval('public.agent_messages_id_seq'::regclass);



ALTER TABLE ONLY public.agent_telemetry_logs ALTER COLUMN id SET DEFAULT nextval('public.agent_telemetry_logs_id_seq'::regclass);



ALTER TABLE ONLY public.ai_diagnoses ALTER COLUMN id SET DEFAULT nextval('public.ai_diagnoses_id_seq'::regclass);



ALTER TABLE ONLY public.ai_quiz_generations ALTER COLUMN id SET DEFAULT nextval('public.ai_quiz_generations_id_seq'::regclass);



ALTER TABLE ONLY public.document_chunks ALTER COLUMN id SET DEFAULT nextval('public.document_chunks_id_seq'::regclass);



ALTER TABLE ONLY public.embedding_reindex_jobs ALTER COLUMN id SET DEFAULT nextval('public.embedding_reindex_jobs_id_seq'::regclass);



ALTER TABLE ONLY public.flashcard_repetitions ALTER COLUMN id SET DEFAULT nextval('public.flashcard_repetitions_id_seq'::regclass);



ALTER TABLE ONLY public.flashcards ALTER COLUMN id SET DEFAULT nextval('public.flashcards_id_seq'::regclass);



ALTER TABLE ONLY public.graph_consolidation_log ALTER COLUMN id SET DEFAULT nextval('public.graph_consolidation_log_id_seq'::regclass);



ALTER TABLE ONLY public.knowledge_node_relations ALTER COLUMN id SET DEFAULT nextval('public.knowledge_node_relations_id_seq'::regclass);



ALTER TABLE ONLY public.knowledge_nodes ALTER COLUMN id SET DEFAULT nextval('public.knowledge_nodes_id_seq'::regclass);



ALTER TABLE ONLY public.llm_api_keys ALTER COLUMN id SET DEFAULT nextval('public.llm_api_keys_id_seq'::regclass);



ALTER TABLE ONLY public.llm_models ALTER COLUMN id SET DEFAULT nextval('public.llm_models_id_seq'::regclass);



ALTER TABLE ONLY public.llm_providers ALTER COLUMN id SET DEFAULT nextval('public.llm_providers_id_seq'::regclass);



ALTER TABLE ONLY public.llm_usage_log ALTER COLUMN id SET DEFAULT nextval('public.llm_usage_log_id_seq'::regclass);



ALTER TABLE ONLY public.mcp_api_keys ALTER COLUMN id SET DEFAULT nextval('public.mcp_api_keys_id_seq'::regclass);



ALTER TABLE ONLY public.mcp_audit_log ALTER COLUMN id SET DEFAULT nextval('public.mcp_audit_log_id_seq'::regclass);



ALTER TABLE ONLY public.personal_flashcard_decks ALTER COLUMN id SET DEFAULT nextval('public.personal_flashcard_decks_id_seq'::regclass);



ALTER TABLE ONLY public.personal_flashcards ALTER COLUMN id SET DEFAULT nextval('public.personal_flashcards_id_seq'::regclass);



ALTER TABLE ONLY public.spaced_repetitions ALTER COLUMN id SET DEFAULT nextval('public.spaced_repetitions_id_seq'::regclass);



ALTER TABLE ONLY public.student_facts ALTER COLUMN id SET DEFAULT nextval('public.student_facts_id_seq'::regclass);



ALTER TABLE ONLY public.student_knowledge_progress ALTER COLUMN id SET DEFAULT nextval('public.student_knowledge_progress_id_seq'::regclass);



ALTER TABLE ONLY public.task_model_bindings ALTER COLUMN id SET DEFAULT nextval('public.task_model_bindings_id_seq'::regclass);



ALTER TABLE ONLY public.agent_episodes
    ADD CONSTRAINT agent_episodes_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.agent_message_feedback
    ADD CONSTRAINT agent_message_feedback_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.agent_messages
    ADD CONSTRAINT agent_messages_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.agent_sessions
    ADD CONSTRAINT agent_sessions_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.agent_telemetry_logs
    ADD CONSTRAINT agent_telemetry_logs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.ai_diagnoses
    ADD CONSTRAINT ai_diagnoses_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.ai_quiz_generations
    ADD CONSTRAINT ai_quiz_generations_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.content_index_status
    ADD CONSTRAINT content_index_status_pkey PRIMARY KEY (content_id);



ALTER TABLE ONLY public.course_blueprints
    ADD CONSTRAINT course_blueprints_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.course_material_routing_jobs
    ADD CONSTRAINT course_material_routing_jobs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT document_chunks_chunk_hash_key UNIQUE (chunk_hash);



ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT document_chunks_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.embedding_reindex_jobs
    ADD CONSTRAINT embedding_reindex_jobs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.flashcard_repetitions
    ADD CONSTRAINT flashcard_repetitions_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.flashcard_repetitions
    ADD CONSTRAINT flashcard_repetitions_student_id_flashcard_id_key UNIQUE (student_id, flashcard_id);



ALTER TABLE ONLY public.flashcards
    ADD CONSTRAINT flashcards_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.graph_consolidation_log
    ADD CONSTRAINT graph_consolidation_log_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.knowledge_node_relations
    ADD CONSTRAINT knowledge_node_relations_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.knowledge_node_relations
    ADD CONSTRAINT knowledge_node_relations_source_node_id_target_node_id_rela_key UNIQUE (source_node_id, target_node_id, relation_type);



ALTER TABLE ONLY public.knowledge_nodes
    ADD CONSTRAINT knowledge_nodes_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.lab_authoring_jobs
    ADD CONSTRAINT lab_authoring_jobs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.llm_api_keys
    ADD CONSTRAINT llm_api_keys_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.llm_api_keys
    ADD CONSTRAINT llm_api_keys_provider_id_alias_key UNIQUE (provider_id, alias);



ALTER TABLE ONLY public.llm_models
    ADD CONSTRAINT llm_models_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.llm_models
    ADD CONSTRAINT llm_models_provider_id_model_name_key UNIQUE (provider_id, model_name);



ALTER TABLE ONLY public.llm_providers
    ADD CONSTRAINT llm_providers_code_key UNIQUE (code);



ALTER TABLE ONLY public.llm_providers
    ADD CONSTRAINT llm_providers_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.llm_usage_log
    ADD CONSTRAINT llm_usage_log_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.mcp_api_keys
    ADD CONSTRAINT mcp_api_keys_key_hash_key UNIQUE (key_hash);



ALTER TABLE ONLY public.mcp_api_keys
    ADD CONSTRAINT mcp_api_keys_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.mcp_audit_log
    ADD CONSTRAINT mcp_audit_log_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.mcp_authoring_requests
    ADD CONSTRAINT mcp_authoring_requests_pkey PRIMARY KEY (owner_id, request_id);



ALTER TABLE ONLY public.personal_flashcard_decks
    ADD CONSTRAINT personal_flashcard_decks_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.personal_flashcard_jobs
    ADD CONSTRAINT personal_flashcard_jobs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.personal_flashcard_reviews
    ADD CONSTRAINT personal_flashcard_reviews_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.personal_flashcards
    ADD CONSTRAINT personal_flashcards_legacy_id_key UNIQUE (legacy_id);



ALTER TABLE ONLY public.personal_flashcards
    ADD CONSTRAINT personal_flashcards_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.quiz_insight_results
    ADD CONSTRAINT quiz_insight_results_pkey PRIMARY KEY (job_id);



ALTER TABLE ONLY public.review_delivery_receipts
    ADD CONSTRAINT review_delivery_receipts_pkey PRIMARY KEY (event_id);



ALTER TABLE ONLY public.spaced_repetitions
    ADD CONSTRAINT spaced_repetitions_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.spaced_repetitions
    ADD CONSTRAINT spaced_repetitions_student_id_question_id_key UNIQUE (student_id, question_id);



ALTER TABLE ONLY public.speech_jobs
    ADD CONSTRAINT speech_jobs_owner_id_content_hash_key UNIQUE (owner_id, content_hash);



ALTER TABLE ONLY public.speech_jobs
    ADD CONSTRAINT speech_jobs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.student_facts
    ADD CONSTRAINT student_facts_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.student_knowledge_progress
    ADD CONSTRAINT student_knowledge_progress_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.student_knowledge_progress
    ADD CONSTRAINT student_knowledge_progress_student_id_node_id_key UNIQUE (student_id, node_id);



ALTER TABLE ONLY public.studio_jobs
    ADD CONSTRAINT studio_jobs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.studio_legacy_media_swept
    ADD CONSTRAINT studio_legacy_media_swept_pkey PRIMARY KEY (project_id);



ALTER TABLE ONLY public.studio_projects
    ADD CONSTRAINT studio_projects_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.studio_shared_youtube_connection
    ADD CONSTRAINT studio_shared_youtube_connection_pkey PRIMARY KEY (singleton);



ALTER TABLE ONLY public.studio_temporary_media
    ADD CONSTRAINT studio_temporary_media_object_key_key UNIQUE (object_key);



ALTER TABLE ONLY public.studio_temporary_media
    ADD CONSTRAINT studio_temporary_media_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.studio_youtube_uploads
    ADD CONSTRAINT studio_youtube_uploads_asset_id_key UNIQUE (asset_id);



ALTER TABLE ONLY public.studio_youtube_uploads
    ADD CONSTRAINT studio_youtube_uploads_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.task_model_bindings
    ADD CONSTRAINT task_model_bindings_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.task_model_bindings
    ADD CONSTRAINT task_model_bindings_task_code_model_id_key UNIQUE (task_code, model_id);



ALTER TABLE ONLY public.agent_message_feedback
    ADD CONSTRAINT uq_feedback_message_user UNIQUE (message_id, user_id);



ALTER TABLE ONLY public.user_concept_mastery
    ADD CONSTRAINT user_concept_mastery_pkey PRIMARY KEY (user_id, concept_id);



CREATE INDEX idx_ad_cache_lookup ON public.ai_diagnoses USING btree (question_id, md5(wrong_answer)) WHERE (question_id IS NOT NULL);



CREATE INDEX idx_ad_node ON public.ai_diagnoses USING btree (node_id);



CREATE INDEX idx_ad_question ON public.ai_diagnoses USING btree (question_id);



CREATE INDEX idx_ad_student ON public.ai_diagnoses USING btree (student_id);



CREATE INDEX idx_ad_student_node ON public.ai_diagnoses USING btree (student_id, node_id, created_at DESC) WHERE (node_id IS NOT NULL);



CREATE INDEX idx_ae_session ON public.agent_episodes USING btree (session_id);



CREATE INDEX idx_ae_user ON public.agent_episodes USING btree (user_id, agent_type);



CREATE INDEX idx_ae_user_course ON public.agent_episodes USING btree (user_id, agent_type, course_id) WHERE (course_id IS NOT NULL);



CREATE INDEX idx_agent_telemetry_created_at ON public.agent_telemetry_logs USING btree (created_at);



CREATE INDEX idx_agent_telemetry_session_id ON public.agent_telemetry_logs USING btree (session_id);



CREATE INDEX idx_aiqg_course ON public.ai_quiz_generations USING btree (course_id);



CREATE INDEX idx_aiqg_course_status_node ON public.ai_quiz_generations USING btree (course_id, status, node_id);



CREATE INDEX idx_aiqg_node ON public.ai_quiz_generations USING btree (node_id);



CREATE INDEX idx_aiqg_status ON public.ai_quiz_generations USING btree (status);



CREATE INDEX idx_am_session ON public.agent_messages USING btree (session_id, created_at);



CREATE INDEX idx_as_active ON public.agent_sessions USING btree (last_active_at);



CREATE INDEX idx_as_course ON public.agent_sessions USING btree (course_id) WHERE (course_id IS NOT NULL);



CREATE INDEX idx_as_user ON public.agent_sessions USING btree (user_id, agent_type);



CREATE INDEX idx_ccm_course ON public.concept_chunk_map USING btree (course_id);



CREATE UNIQUE INDEX idx_ccm_node_course ON public.concept_chunk_map USING btree (node_id, course_id);



CREATE INDEX idx_chunks_child_level ON public.document_chunks USING btree (course_id, id) WHERE (((status)::text = 'ready'::text) AND ((chunk_level)::text = 'child'::text));



CREATE INDEX idx_chunks_node_covering ON public.document_chunks USING btree (node_id, id, content_id, course_id, chunk_level) WHERE (((status)::text = 'ready'::text) AND (node_id IS NOT NULL));



CREATE INDEX idx_chunks_node_status ON public.document_chunks USING btree (node_id, status) WHERE (((status)::text = 'ready'::text) AND (node_id IS NOT NULL));



CREATE INDEX idx_cis_course ON public.content_index_status USING btree (course_id);



CREATE INDEX idx_cis_course_status ON public.content_index_status USING btree (course_id, status);



CREATE INDEX idx_cis_status ON public.content_index_status USING btree (status);



CREATE INDEX idx_course_blueprints_owner_status ON public.course_blueprints USING btree (owner_id, status, updated_at DESC);



CREATE INDEX idx_course_blueprints_recovery ON public.course_blueprints USING btree (status, lease_until, updated_at) WHERE ((status)::text = 'PROCESSING'::text);



CREATE INDEX idx_dc_content ON public.document_chunks USING btree (content_id);



CREATE INDEX idx_dc_content_status ON public.document_chunks USING btree (content_id, status);



CREATE INDEX idx_dc_course ON public.document_chunks USING btree (course_id);



CREATE INDEX idx_dc_fts_simple ON public.document_chunks USING gin (to_tsvector('simple'::regconfig, chunk_text));



CREATE INDEX idx_dc_hash ON public.document_chunks USING btree (chunk_hash);



CREATE INDEX idx_dc_level ON public.document_chunks USING btree (chunk_level);



CREATE INDEX idx_dc_node ON public.document_chunks USING btree (node_id);



CREATE INDEX idx_dc_node_status ON public.document_chunks USING btree (node_id, status) WHERE (node_id IS NOT NULL);



CREATE INDEX idx_dc_parent ON public.document_chunks USING btree (parent_chunk_id);



CREATE INDEX idx_dc_status ON public.document_chunks USING btree (status);



CREATE INDEX idx_dc_trgm ON public.document_chunks USING gin (chunk_text public.gin_trgm_ops);



CREATE INDEX idx_erj_content ON public.embedding_reindex_jobs USING btree (content_id);



CREATE INDEX idx_erj_course ON public.embedding_reindex_jobs USING btree (course_id);



CREATE INDEX idx_erj_status ON public.embedding_reindex_jobs USING btree (status);



CREATE INDEX idx_fc_course ON public.flashcards USING btree (course_id);



CREATE INDEX idx_fc_lesson ON public.flashcards USING btree (lesson_id);



CREATE INDEX idx_fc_student_course_node ON public.flashcards USING btree (student_id, course_id, node_id) WHERE ((status)::text = 'ACTIVE'::text);



CREATE INDEX idx_fc_student_node ON public.flashcards USING btree (student_id, node_id);



CREATE INDEX idx_fcr_due ON public.flashcard_repetitions USING btree (student_id, course_id, next_review_date);



CREATE INDEX idx_fcr_student_due_today ON public.flashcard_repetitions USING btree (student_id, course_id, next_review_date) INCLUDE (flashcard_id, easiness_factor, interval_days, repetitions) WHERE (next_review_date IS NOT NULL);



CREATE INDEX idx_feedback_recent ON public.agent_message_feedback USING btree (user_id, created_at DESC);



CREATE INDEX idx_feedback_session ON public.agent_message_feedback USING btree (session_id);



CREATE INDEX idx_flashcards_content_id ON public.flashcards USING btree (content_id);



CREATE INDEX idx_gcl_course ON public.graph_consolidation_log USING btree (course_id);



CREATE INDEX idx_gcl_created ON public.graph_consolidation_log USING btree (created_at DESC);



CREATE INDEX idx_gcl_survivor ON public.graph_consolidation_log USING btree (survivor_id);



CREATE INDEX idx_kn_course ON public.knowledge_nodes USING btree (course_id);



CREATE INDEX idx_kn_course_managed ON public.knowledge_nodes USING btree (course_id, managed_by) WHERE (managed_by IS NOT NULL);



CREATE INDEX idx_kn_level ON public.knowledge_nodes USING btree (course_id, level);



CREATE INDEX idx_kn_parent ON public.knowledge_nodes USING btree (parent_id);



CREATE INDEX idx_kn_source ON public.knowledge_nodes USING btree (source_content_id) WHERE (source_content_id IS NOT NULL);



CREATE INDEX idx_kn_source_content ON public.knowledge_nodes USING btree (source_content_id, source_content_title) WHERE (source_content_id IS NOT NULL);



CREATE INDEX idx_knr_course ON public.knowledge_node_relations USING btree (course_id);



CREATE INDEX idx_knr_source ON public.knowledge_node_relations USING btree (source_node_id);



CREATE INDEX idx_knr_target ON public.knowledge_node_relations USING btree (target_node_id);



CREATE INDEX idx_llm_api_keys_pool ON public.llm_api_keys USING btree (provider_id, status, cooldown_until);



CREATE INDEX idx_llm_models_provider ON public.llm_models USING btree (provider_id, enabled);



CREATE INDEX idx_material_routing_recovery ON public.course_material_routing_jobs USING btree (status, lease_until, updated_at) WHERE ((status)::text = 'PROCESSING'::text);



CREATE INDEX idx_mcp_api_keys_hash_active ON public.mcp_api_keys USING btree (key_hash) WHERE (revoked_at IS NULL);



CREATE INDEX idx_mcp_api_keys_user ON public.mcp_api_keys USING btree (user_id, created_at DESC);



CREATE INDEX idx_mcp_audit_user_created ON public.mcp_audit_log USING btree (user_id, created_at DESC);



CREATE INDEX idx_quiz_insight_results_created_at ON public.quiz_insight_results USING btree (created_at);



CREATE INDEX idx_sf_unsynced ON public.student_facts USING btree (qdrant_synced) WHERE (NOT qdrant_synced);



CREATE INDEX idx_sf_user ON public.student_facts USING btree (user_id);



CREATE INDEX idx_sf_user_cat ON public.student_facts USING btree (user_id, category);



CREATE INDEX idx_skp_mastery ON public.student_knowledge_progress USING btree (mastery_level);



CREATE INDEX idx_skp_node ON public.student_knowledge_progress USING btree (node_id);



CREATE INDEX idx_skp_node_course ON public.student_knowledge_progress USING btree (node_id, course_id);



CREATE INDEX idx_skp_student_course ON public.student_knowledge_progress USING btree (student_id, course_id);



CREATE INDEX idx_sr_course ON public.spaced_repetitions USING btree (student_id, course_id);



CREATE INDEX idx_sr_course_date ON public.spaced_repetitions USING btree (student_id, course_id, next_review_date);



CREATE INDEX idx_sr_due ON public.spaced_repetitions USING btree (student_id, next_review_date);



CREATE INDEX idx_sr_student_due_today ON public.spaced_repetitions USING btree (student_id, course_id, next_review_date) INCLUDE (question_id, easiness_factor, interval_days, repetitions) WHERE (next_review_date IS NOT NULL);



CREATE INDEX idx_studio_course ON public.studio_projects USING btree (course_id, created_at DESC);



CREATE INDEX idx_task_bindings_chain ON public.task_model_bindings USING btree (task_code, enabled, priority);



CREATE INDEX idx_ucm_concept ON public.user_concept_mastery USING btree (concept_id);



CREATE INDEX idx_ucm_user_concept ON public.user_concept_mastery USING btree (user_id, concept_id);



CREATE INDEX idx_usage_log_created ON public.llm_usage_log USING btree (created_at DESC);



CREATE INDEX idx_usage_log_key ON public.llm_usage_log USING btree (api_key_id, created_at DESC);



CREATE INDEX idx_usage_log_model ON public.llm_usage_log USING btree (model_id, created_at DESC);



CREATE INDEX idx_usage_log_task ON public.llm_usage_log USING btree (task_code, created_at DESC);



CREATE INDEX lab_authoring_jobs_owner ON public.lab_authoring_jobs USING btree (owner_id, created_at DESC);



CREATE INDEX lab_authoring_jobs_pending ON public.lab_authoring_jobs USING btree (status, created_at);



CREATE UNIQUE INDEX personal_deck_content ON public.personal_flashcard_decks USING btree (student_id, course_id, source_content_id) WHERE (source_content_id IS NOT NULL);



CREATE UNIQUE INDEX personal_deck_lesson ON public.personal_flashcard_decks USING btree (student_id, course_id, source_lesson_id) WHERE (source_lesson_id IS NOT NULL);



CREATE INDEX personal_flashcard_decks_student_id_course_id_idx ON public.personal_flashcard_decks USING btree (student_id, course_id);



CREATE INDEX personal_flashcard_decks_student_id_idx ON public.personal_flashcard_decks USING btree (student_id);



CREATE INDEX personal_flashcard_jobs_student_id_course_id_created_at_idx ON public.personal_flashcard_jobs USING btree (student_id, course_id, created_at);



CREATE INDEX personal_flashcard_jobs_student_id_created_at_idx ON public.personal_flashcard_jobs USING btree (student_id, created_at);



CREATE INDEX personal_flashcards_student_id_deck_id_due_at_idx ON public.personal_flashcards USING btree (student_id, deck_id, due_at);



CREATE INDEX speech_pending_jobs ON public.speech_jobs USING btree (status, lease_until);



CREATE INDEX studio_media_expiry ON public.studio_temporary_media USING btree (expires_at, cleanup_after) WHERE (deleted_at IS NULL);



CREATE INDEX studio_media_project ON public.studio_temporary_media USING btree (project_id, generation);



CREATE UNIQUE INDEX studio_one_active_job ON public.studio_jobs USING btree (project_id) WHERE (status = ANY (ARRAY['queued'::text, 'running'::text]));



CREATE INDEX studio_pending_jobs ON public.studio_jobs USING btree (status, lease_until, created_at);



CREATE INDEX studio_youtube_queue ON public.studio_youtube_uploads USING btree (status, lease_until, created_at);



CREATE UNIQUE INDEX uq_flashcard_student_node_front ON public.flashcards USING btree (student_id, course_id, node_id, md5(front_text)) WHERE ((node_id IS NOT NULL) AND ((status)::text = 'ACTIVE'::text));



CREATE UNIQUE INDEX uq_kn_course_external_key ON public.knowledge_nodes USING btree (course_id, external_key) WHERE (external_key IS NOT NULL);



CREATE TRIGGER tr_aiqg_updated BEFORE UPDATE ON public.ai_quiz_generations FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER tr_course_blueprints_updated BEFORE UPDATE ON public.course_blueprints FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER tr_erj_updated BEFORE UPDATE ON public.embedding_reindex_jobs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER tr_fc_updated BEFORE UPDATE ON public.flashcards FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER tr_fcr_updated BEFORE UPDATE ON public.flashcard_repetitions FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER tr_kn_updated BEFORE UPDATE ON public.knowledge_nodes FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER tr_skp_updated BEFORE UPDATE ON public.student_knowledge_progress FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER tr_sr_updated BEFORE UPDATE ON public.spaced_repetitions FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER trg_llm_api_keys_updated BEFORE UPDATE ON public.llm_api_keys FOR EACH ROW EXECUTE FUNCTION public.trg_llm_touch_updated_at();



CREATE TRIGGER trg_llm_models_updated BEFORE UPDATE ON public.llm_models FOR EACH ROW EXECUTE FUNCTION public.trg_llm_touch_updated_at();



CREATE TRIGGER trg_llm_providers_updated BEFORE UPDATE ON public.llm_providers FOR EACH ROW EXECUTE FUNCTION public.trg_llm_touch_updated_at();



CREATE TRIGGER trg_task_bindings_updated BEFORE UPDATE ON public.task_model_bindings FOR EACH ROW EXECUTE FUNCTION public.trg_llm_touch_updated_at();



ALTER TABLE ONLY public.agent_episodes
    ADD CONSTRAINT agent_episodes_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.agent_sessions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.agent_message_feedback
    ADD CONSTRAINT agent_message_feedback_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.agent_messages(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.agent_message_feedback
    ADD CONSTRAINT agent_message_feedback_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.agent_sessions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.agent_messages
    ADD CONSTRAINT agent_messages_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.agent_sessions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.ai_diagnoses
    ADD CONSTRAINT ai_diagnoses_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.knowledge_nodes(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.ai_diagnoses
    ADD CONSTRAINT ai_diagnoses_source_chunk_id_fkey FOREIGN KEY (source_chunk_id) REFERENCES public.document_chunks(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.ai_quiz_generations
    ADD CONSTRAINT ai_quiz_generations_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.knowledge_nodes(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.ai_quiz_generations
    ADD CONSTRAINT ai_quiz_generations_source_chunk_id_fkey FOREIGN KEY (source_chunk_id) REFERENCES public.document_chunks(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT document_chunks_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.knowledge_nodes(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT document_chunks_parent_chunk_id_fkey FOREIGN KEY (parent_chunk_id) REFERENCES public.document_chunks(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.flashcard_repetitions
    ADD CONSTRAINT flashcard_repetitions_flashcard_id_fkey FOREIGN KEY (flashcard_id) REFERENCES public.flashcards(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.flashcards
    ADD CONSTRAINT flashcards_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.knowledge_nodes(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.flashcards
    ADD CONSTRAINT flashcards_source_diagnosis_id_fkey FOREIGN KEY (source_diagnosis_id) REFERENCES public.ai_diagnoses(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.knowledge_node_relations
    ADD CONSTRAINT knowledge_node_relations_source_node_id_fkey FOREIGN KEY (source_node_id) REFERENCES public.knowledge_nodes(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.knowledge_node_relations
    ADD CONSTRAINT knowledge_node_relations_target_node_id_fkey FOREIGN KEY (target_node_id) REFERENCES public.knowledge_nodes(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.knowledge_nodes
    ADD CONSTRAINT knowledge_nodes_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.knowledge_nodes(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.llm_api_keys
    ADD CONSTRAINT llm_api_keys_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.llm_providers(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.llm_models
    ADD CONSTRAINT llm_models_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.llm_providers(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.llm_usage_log
    ADD CONSTRAINT llm_usage_log_api_key_id_fkey FOREIGN KEY (api_key_id) REFERENCES public.llm_api_keys(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.llm_usage_log
    ADD CONSTRAINT llm_usage_log_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.llm_models(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.mcp_audit_log
    ADD CONSTRAINT mcp_audit_log_key_id_fkey FOREIGN KEY (key_id) REFERENCES public.mcp_api_keys(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.personal_flashcard_reviews
    ADD CONSTRAINT personal_flashcard_reviews_card_id_fkey FOREIGN KEY (card_id) REFERENCES public.personal_flashcards(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.personal_flashcards
    ADD CONSTRAINT personal_flashcards_deck_id_fkey FOREIGN KEY (deck_id) REFERENCES public.personal_flashcard_decks(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.spaced_repetitions
    ADD CONSTRAINT spaced_repetitions_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.knowledge_nodes(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.speech_jobs
    ADD CONSTRAINT speech_jobs_card_id_fkey FOREIGN KEY (card_id) REFERENCES public.personal_flashcards(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.student_knowledge_progress
    ADD CONSTRAINT student_knowledge_progress_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.knowledge_nodes(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.studio_jobs
    ADD CONSTRAINT studio_jobs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.studio_projects(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.studio_youtube_uploads
    ADD CONSTRAINT studio_youtube_uploads_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES public.studio_temporary_media(id);



ALTER TABLE ONLY public.task_model_bindings
    ADD CONSTRAINT task_model_bindings_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.llm_models(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.user_concept_mastery
    ADD CONSTRAINT user_concept_mastery_concept_id_fkey FOREIGN KEY (concept_id) REFERENCES public.knowledge_nodes(id) ON DELETE CASCADE;

-- Default rows from repository SQL only.
SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;



































































































































SELECT pg_catalog.setval('public.agent_message_feedback_id_seq', 1, false);



SELECT pg_catalog.setval('public.agent_messages_id_seq', 1, false);



SELECT pg_catalog.setval('public.agent_telemetry_logs_id_seq', 1, false);



SELECT pg_catalog.setval('public.ai_diagnoses_id_seq', 1, false);



SELECT pg_catalog.setval('public.ai_quiz_generations_id_seq', 1, false);



SELECT pg_catalog.setval('public.document_chunks_id_seq', 1, false);



SELECT pg_catalog.setval('public.embedding_reindex_jobs_id_seq', 1, false);



SELECT pg_catalog.setval('public.flashcard_repetitions_id_seq', 1, false);



SELECT pg_catalog.setval('public.flashcards_id_seq', 1, false);



SELECT pg_catalog.setval('public.graph_consolidation_log_id_seq', 1, false);



SELECT pg_catalog.setval('public.knowledge_node_relations_id_seq', 1, false);



SELECT pg_catalog.setval('public.knowledge_nodes_id_seq', 1, false);



SELECT pg_catalog.setval('public.llm_api_keys_id_seq', 1, false);



SELECT pg_catalog.setval('public.llm_models_id_seq', 1, false);



SELECT pg_catalog.setval('public.llm_providers_id_seq', 1, false);



SELECT pg_catalog.setval('public.llm_usage_log_id_seq', 1, false);



SELECT pg_catalog.setval('public.mcp_api_keys_id_seq', 1, false);



SELECT pg_catalog.setval('public.mcp_audit_log_id_seq', 1, false);



SELECT pg_catalog.setval('public.personal_flashcard_decks_id_seq', 1, false);



SELECT pg_catalog.setval('public.personal_flashcards_id_seq', 1, false);



SELECT pg_catalog.setval('public.spaced_repetitions_id_seq', 1, false);



SELECT pg_catalog.setval('public.student_facts_id_seq', 1, false);



SELECT pg_catalog.setval('public.student_knowledge_progress_id_seq', 1, false);



SELECT pg_catalog.setval('public.task_model_bindings_id_seq', 1, false);
