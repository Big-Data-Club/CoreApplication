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

SET default_tablespace = '';

SET default_table_access_method = heap;


CREATE TABLE public.datasets (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    description text DEFAULT ''::text,
    minio_key character varying(500) NOT NULL,
    file_size bigint DEFAULT 0,
    format character varying(50) DEFAULT ''::character varying,
    is_public boolean DEFAULT false,
    created_by bigint NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.datasets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.datasets_id_seq OWNED BY public.datasets.id;



CREATE TABLE public.environment_templates (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    description text DEFAULT ''::text,
    compute_backend character varying(20) DEFAULT 'K8S'::character varying NOT NULL,
    docker_image character varying(500) DEFAULT 'ubuntu:22.04'::character varying NOT NULL,
    cpu_milli integer DEFAULT 500 NOT NULL,
    memory_mb integer DEFAULT 512 NOT NULL,
    gpu_count integer DEFAULT 0 NOT NULL,
    disk_size_mb integer DEFAULT 1024 NOT NULL,
    allowed_ports jsonb DEFAULT '[]'::jsonb,
    startup_script text DEFAULT ''::text,
    packages jsonb DEFAULT '[]'::jsonb,
    slurm_partition character varying(100) DEFAULT ''::character varying,
    slurm_account character varying(100) DEFAULT ''::character varying,
    slurm_qos character varying(100) DEFAULT ''::character varying,
    slurm_max_time character varying(20) DEFAULT '01:00:00'::character varying,
    created_by bigint NOT NULL,
    is_public boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT environment_templates_compute_backend_check CHECK (((compute_backend)::text = ANY (ARRAY[('K8S'::character varying)::text, ('SLURM'::character varying)::text])))
);



CREATE SEQUENCE public.environment_templates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.environment_templates_id_seq OWNED BY public.environment_templates.id;



CREATE TABLE public.evidence_events (
    event_id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_event_id uuid NOT NULL,
    schema_version integer DEFAULT 1 NOT NULL,
    run_id bigint NOT NULL,
    trial_id bigint,
    seq_no bigint NOT NULL,
    actor_id bigint NOT NULL,
    actor_type character varying(20) NOT NULL,
    verb character varying(60) NOT NULL,
    object_data jsonb NOT NULL,
    result_data jsonb DEFAULT '{}'::jsonb NOT NULL,
    context_data jsonb DEFAULT '{}'::jsonb NOT NULL,
    sim_time_ms bigint,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT evidence_events_actor_type_check CHECK (((actor_type)::text = ANY (ARRAY[('LEARNER'::character varying)::text, ('TEACHER'::character varying)::text, ('SYSTEM'::character varying)::text]))),
    CONSTRAINT evidence_events_schema_version_check CHECK ((schema_version > 0)),
    CONSTRAINT evidence_events_seq_no_check CHECK ((seq_no > 0)),
    CONSTRAINT evidence_events_sim_time_ms_check CHECK (((sim_time_ms IS NULL) OR (sim_time_ms >= 0)))
);



CREATE TABLE public.experiment_definitions (
    lab_version_id bigint NOT NULL,
    domain character varying(20) NOT NULL,
    inquiry_level character varying(30) NOT NULL,
    workflow_schema_version integer DEFAULT 1 NOT NULL,
    model_version character varying(100) NOT NULL,
    learning_objectives jsonb DEFAULT '[]'::jsonb NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT experiment_definitions_domain_check CHECK (((domain)::text = ANY (ARRAY[('PLANT'::character varying)::text, ('ROBOT'::character varying)::text, ('CHEMISTRY'::character varying)::text]))),
    CONSTRAINT experiment_definitions_inquiry_level_check CHECK (((inquiry_level)::text = ANY (ARRAY[('STRUCTURED'::character varying)::text, ('GUIDED'::character varying)::text, ('OPEN_INQUIRY'::character varying)::text]))),
    CONSTRAINT experiment_definitions_workflow_schema_version_check CHECK ((workflow_schema_version > 0))
);



CREATE TABLE public.experiment_trials (
    id bigint NOT NULL,
    run_id bigint NOT NULL,
    trial_number integer NOT NULL,
    seed bigint NOT NULL,
    model_version character varying(100) NOT NULL,
    config_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    status character varying(20) DEFAULT 'READY'::character varying NOT NULL,
    started_at timestamp with time zone,
    ended_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT experiment_trials_seed_check CHECK ((seed >= 0)),
    CONSTRAINT experiment_trials_status_check CHECK (((status)::text = ANY (ARRAY[('READY'::character varying)::text, ('RUNNING'::character varying)::text, ('PAUSED'::character varying)::text, ('COMPLETED'::character varying)::text, ('FAILED'::character varying)::text, ('CANCELLED'::character varying)::text]))),
    CONSTRAINT experiment_trials_trial_number_check CHECK ((trial_number > 0))
);



CREATE SEQUENCE public.experiment_trials_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.experiment_trials_id_seq OWNED BY public.experiment_trials.id;



CREATE TABLE public.experiment_variables (
    lab_version_id bigint NOT NULL,
    variable_key character varying(100) NOT NULL,
    display_name character varying(255) NOT NULL,
    variable_role character varying(20) NOT NULL,
    data_type character varying(20) NOT NULL,
    unit character varying(50) DEFAULT ''::character varying NOT NULL,
    min_value double precision,
    max_value double precision,
    default_value jsonb,
    source_id character varying(255) DEFAULT ''::character varying NOT NULL,
    CONSTRAINT experiment_variables_check CHECK (((min_value IS NULL) OR (max_value IS NULL) OR (min_value <= max_value))),
    CONSTRAINT experiment_variables_data_type_check CHECK (((data_type)::text = ANY (ARRAY[('NUMBER'::character varying)::text, ('INTEGER'::character varying)::text, ('BOOLEAN'::character varying)::text, ('STRING'::character varying)::text]))),
    CONSTRAINT experiment_variables_variable_role_check CHECK (((variable_role)::text = ANY (ARRAY[('INDEPENDENT'::character varying)::text, ('DEPENDENT'::character varying)::text, ('CONTROLLED'::character varying)::text])))
);



CREATE TABLE public.lab_datasets (
    lab_id bigint NOT NULL,
    dataset_id bigint NOT NULL,
    mount_path character varying(500) DEFAULT '/data'::character varying NOT NULL
);



CREATE TABLE public.lab_enrollments (
    id bigint NOT NULL,
    lab_id bigint NOT NULL,
    user_id bigint NOT NULL,
    status character varying(20) DEFAULT 'ACCEPTED'::character varying NOT NULL,
    enrolled_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT lab_enrollments_status_check CHECK (((status)::text = ANY (ARRAY[('WAITING'::character varying)::text, ('ACCEPTED'::character varying)::text, ('REJECTED'::character varying)::text])))
);



CREATE SEQUENCE public.lab_enrollments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.lab_enrollments_id_seq OWNED BY public.lab_enrollments.id;



CREATE TABLE public.lab_leaderboard (
    id bigint NOT NULL,
    lab_id bigint NOT NULL,
    user_id bigint NOT NULL,
    best_submission_id bigint,
    best_score numeric(7,2) DEFAULT 0,
    best_runtime_ms integer DEFAULT 0,
    best_memory_kb integer DEFAULT 0,
    attempt_count integer DEFAULT 0,
    first_accepted_at timestamp without time zone,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.lab_leaderboard_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.lab_leaderboard_id_seq OWNED BY public.lab_leaderboard.id;



CREATE TABLE public.lab_runs (
    id bigint NOT NULL,
    lab_version_id bigint NOT NULL,
    user_id bigint NOT NULL,
    idempotency_key character varying(128) NOT NULL,
    status character varying(20) DEFAULT 'ACTIVE'::character varying NOT NULL,
    current_node_key character varying(100),
    last_event_seq bigint DEFAULT 0 NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    ended_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT lab_runs_status_check CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('COMPLETED'::character varying)::text, ('ABANDONED'::character varying)::text])))
);



CREATE SEQUENCE public.lab_runs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.lab_runs_id_seq OWNED BY public.lab_runs.id;



CREATE TABLE public.lab_runtime_task_attempts (
    id bigint NOT NULL,
    task_id bigint NOT NULL,
    lab_id bigint NOT NULL,
    user_id bigint NOT NULL,
    session_id character varying(100),
    passed boolean NOT NULL,
    message text DEFAULT ''::text NOT NULL,
    evidence jsonb DEFAULT '{}'::jsonb NOT NULL,
    checked_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.lab_runtime_task_attempts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.lab_runtime_task_attempts_id_seq OWNED BY public.lab_runtime_task_attempts.id;



CREATE TABLE public.lab_runtime_tasks (
    id bigint NOT NULL,
    lab_id bigint NOT NULL,
    title character varying(255) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    runtime_type character varying(20) NOT NULL,
    verifier_type character varying(30) NOT NULL,
    verifier_config jsonb DEFAULT '{}'::jsonb NOT NULL,
    weight integer DEFAULT 1 NOT NULL,
    is_required boolean DEFAULT true NOT NULL,
    order_index integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT lab_runtime_tasks_runtime_type_check CHECK (((runtime_type)::text = ANY (ARRAY[('WORKSPACE'::character varying)::text, ('HPC'::character varying)::text]))),
    CONSTRAINT lab_runtime_tasks_verifier_type_check CHECK (((verifier_type)::text = ANY (ARRAY[('FILE_EXISTS'::character varying)::text, ('FILE_CONTAINS'::character varying)::text, ('COMMAND_EXIT'::character varying)::text, ('COMMAND_OUTPUT'::character varying)::text, ('HPC_JOB_SUBMITTED'::character varying)::text, ('HPC_JOB_COMPLETED'::character varying)::text]))),
    CONSTRAINT lab_runtime_tasks_weight_check CHECK (((weight > 0) AND (weight <= 1000)))
);



CREATE SEQUENCE public.lab_runtime_tasks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.lab_runtime_tasks_id_seq OWNED BY public.lab_runtime_tasks.id;



CREATE TABLE public.lab_section_content (
    id bigint NOT NULL,
    section_id bigint NOT NULL,
    type character varying(30) NOT NULL,
    title character varying(255) NOT NULL,
    description text DEFAULT ''::text,
    order_index integer DEFAULT 0 NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    is_published boolean DEFAULT false NOT NULL,
    is_mandatory boolean DEFAULT false NOT NULL,
    file_path character varying(500) DEFAULT ''::character varying,
    file_size bigint DEFAULT 0,
    file_type character varying(50) DEFAULT ''::character varying,
    created_by bigint NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT lab_section_content_type_check CHECK (((type)::text = ANY (ARRAY[('TEXT'::character varying)::text, ('DOCUMENT'::character varying)::text, ('IMAGE'::character varying)::text, ('CODE_TEMPLATE'::character varying)::text, ('CHECKPOINT'::character varying)::text])))
);



CREATE SEQUENCE public.lab_section_content_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.lab_section_content_id_seq OWNED BY public.lab_section_content.id;



CREATE TABLE public.lab_sections (
    id bigint NOT NULL,
    lab_id bigint NOT NULL,
    title character varying(255) NOT NULL,
    description text DEFAULT ''::text,
    order_index integer DEFAULT 0 NOT NULL,
    is_published boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.lab_sections_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.lab_sections_id_seq OWNED BY public.lab_sections.id;



CREATE TABLE public.lab_sessions (
    id bigint NOT NULL,
    lab_id bigint NOT NULL,
    user_id bigint NOT NULL,
    session_token uuid DEFAULT gen_random_uuid() NOT NULL,
    k8s_pod_name character varying(253) DEFAULT ''::character varying,
    k8s_namespace character varying(63) DEFAULT ''::character varying,
    k8s_node character varying(253) DEFAULT ''::character varying,
    k8s_pod_ip character varying(45) DEFAULT ''::character varying,
    ttyd_port integer DEFAULT 7681,
    status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    started_at timestamp without time zone,
    last_active_at timestamp without time zone DEFAULT now(),
    suspended_at timestamp without time zone,
    ended_at timestamp without time zone,
    expires_at timestamp without time zone,
    workspace_snapshot character varying(500) DEFAULT ''::character varying,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT lab_sessions_status_check CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('CREATING'::character varying)::text, ('RUNNING'::character varying)::text, ('SUSPENDED'::character varying)::text, ('STOPPING'::character varying)::text, ('STOPPED'::character varying)::text, ('FAILED'::character varying)::text, ('COMPLETED'::character varying)::text])))
);



CREATE SEQUENCE public.lab_sessions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.lab_sessions_id_seq OWNED BY public.lab_sessions.id;



CREATE TABLE public.lab_submissions (
    id bigint NOT NULL,
    lab_id bigint NOT NULL,
    user_id bigint NOT NULL,
    session_id bigint,
    language character varying(30) DEFAULT ''::character varying,
    code text DEFAULT ''::text,
    query text DEFAULT ''::text,
    files_snapshot character varying(500) DEFAULT ''::character varying,
    notebook_key character varying(500) DEFAULT ''::character varying,
    script_content text DEFAULT ''::text,
    status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    score numeric(7,2) DEFAULT 0,
    max_score numeric(7,2) DEFAULT 100,
    passed_tests integer DEFAULT 0,
    total_tests integer DEFAULT 0,
    runtime_ms integer DEFAULT 0,
    memory_kb integer DEFAULT 0,
    slurm_job_id bigint,
    stdout_key character varying(500) DEFAULT ''::character varying,
    stderr_key character varying(500) DEFAULT ''::character varying,
    exit_code integer,
    feedback jsonb DEFAULT '{}'::jsonb,
    compiler_output text DEFAULT ''::text,
    submitted_at timestamp without time zone DEFAULT now() NOT NULL,
    graded_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT lab_submissions_status_check CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('RUNNING'::character varying)::text, ('ACCEPTED'::character varying)::text, ('WRONG_ANSWER'::character varying)::text, ('TIME_LIMIT'::character varying)::text, ('MEMORY_LIMIT'::character varying)::text, ('RUNTIME_ERROR'::character varying)::text, ('COMPILE_ERROR'::character varying)::text, ('COMPLETED'::character varying)::text, ('FAILED'::character varying)::text, ('CANCELLED'::character varying)::text])))
);



CREATE SEQUENCE public.lab_submissions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.lab_submissions_id_seq OWNED BY public.lab_submissions.id;



CREATE TABLE public.lab_test_cases (
    id bigint NOT NULL,
    lab_id bigint NOT NULL,
    name character varying(255) DEFAULT ''::character varying NOT NULL,
    order_index integer DEFAULT 0 NOT NULL,
    is_sample boolean DEFAULT false NOT NULL,
    is_hidden boolean DEFAULT true NOT NULL,
    weight integer DEFAULT 1 NOT NULL,
    input text DEFAULT ''::text,
    expected text DEFAULT ''::text,
    query_expected text DEFAULT ''::text,
    time_limit_ms integer,
    memory_limit_mb integer,
    explanation text DEFAULT ''::text,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.lab_test_cases_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.lab_test_cases_id_seq OWNED BY public.lab_test_cases.id;



CREATE TABLE public.lab_versions (
    id bigint NOT NULL,
    lab_id bigint NOT NULL,
    version_number integer NOT NULL,
    status character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
    definition_hash character varying(64) NOT NULL,
    definition_snapshot jsonb NOT NULL,
    created_by bigint NOT NULL,
    validated_at timestamp with time zone,
    published_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT lab_versions_status_check CHECK (((status)::text = ANY (ARRAY[('DRAFT'::character varying)::text, ('VALIDATED'::character varying)::text, ('PUBLISHED'::character varying)::text, ('SUPERSEDED'::character varying)::text]))),
    CONSTRAINT lab_versions_version_number_check CHECK ((version_number > 0))
);



CREATE SEQUENCE public.lab_versions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.lab_versions_id_seq OWNED BY public.lab_versions.id;



CREATE TABLE public.labs (
    id bigint NOT NULL,
    title character varying(255) NOT NULL,
    description text DEFAULT ''::text,
    category character varying(100) DEFAULT ''::character varying,
    level character varying(30) DEFAULT 'BEGINNER'::character varying,
    thumbnail_url character varying(500) DEFAULT ''::character varying,
    lab_type character varying(30) DEFAULT 'CODING'::character varying NOT NULL,
    status character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
    runtime_config jsonb DEFAULT '{}'::jsonb NOT NULL,
    environment_template_id bigint,
    max_session_duration_min integer DEFAULT 120 NOT NULL,
    max_concurrent_sessions integer DEFAULT 50 NOT NULL,
    max_submissions integer,
    auto_grade boolean DEFAULT false NOT NULL,
    grading_config jsonb DEFAULT '{}'::jsonb,
    start_time timestamp without time zone,
    deadline timestamp without time zone,
    allow_late_submission boolean DEFAULT false,
    late_penalty_percent integer DEFAULT 0,
    created_by bigint NOT NULL,
    published_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT labs_lab_type_check CHECK (((lab_type)::text = ANY (ARRAY[('CODING'::character varying)::text, ('HPC'::character varying)::text, ('JUPYTER'::character varying)::text, ('WORKSPACE'::character varying)::text, ('DATABASE'::character varying)::text, ('CUSTOM'::character varying)::text, ('PLANT'::character varying)::text, ('ROBOT'::character varying)::text, ('CHEMISTRY'::character varying)::text]))),
    CONSTRAINT labs_level_check CHECK (((level)::text = ANY (ARRAY[('BEGINNER'::character varying)::text, ('INTERMEDIATE'::character varying)::text, ('ADVANCED'::character varying)::text, ('ALL_LEVELS'::character varying)::text]))),
    CONSTRAINT labs_status_check CHECK (((status)::text = ANY (ARRAY[('DRAFT'::character varying)::text, ('PUBLISHED'::character varying)::text, ('ARCHIVED'::character varying)::text])))
);



CREATE SEQUENCE public.labs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.labs_id_seq OWNED BY public.labs.id;



CREATE TABLE public.submission_test_results (
    id bigint NOT NULL,
    submission_id bigint NOT NULL,
    test_case_id bigint NOT NULL,
    status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    actual_output text DEFAULT ''::text,
    runtime_ms integer DEFAULT 0,
    memory_kb integer DEFAULT 0,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT submission_test_results_status_check CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('PASSED'::character varying)::text, ('WRONG_ANSWER'::character varying)::text, ('TIME_LIMIT'::character varying)::text, ('MEMORY_LIMIT'::character varying)::text, ('RUNTIME_ERROR'::character varying)::text, ('COMPILE_ERROR'::character varying)::text])))
);



CREATE SEQUENCE public.submission_test_results_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.submission_test_results_id_seq OWNED BY public.submission_test_results.id;



CREATE TABLE public.users (
    id bigint NOT NULL,
    email character varying(255) NOT NULL,
    full_name character varying(255) DEFAULT ''::character varying NOT NULL,
    roles text[] DEFAULT '{}'::text[] NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    synced_at timestamp without time zone DEFAULT now() NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.workflow_edges (
    id bigint NOT NULL,
    lab_version_id bigint NOT NULL,
    from_node_key character varying(100) NOT NULL,
    to_node_key character varying(100) NOT NULL,
    condition_expression text DEFAULT 'always'::text NOT NULL,
    priority integer DEFAULT 0 NOT NULL
);



CREATE SEQUENCE public.workflow_edges_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.workflow_edges_id_seq OWNED BY public.workflow_edges.id;



CREATE TABLE public.workflow_nodes (
    lab_version_id bigint NOT NULL,
    node_key character varying(100) NOT NULL,
    node_type character varying(40) NOT NULL,
    title character varying(255) NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    required_evidence jsonb DEFAULT '[]'::jsonb NOT NULL,
    order_hint integer DEFAULT 0 NOT NULL,
    CONSTRAINT workflow_nodes_node_type_check CHECK (((node_type)::text = ANY (ARRAY[('INSTRUCTION'::character varying)::text, ('QUESTION'::character varying)::text, ('PREDICTION'::character varying)::text, ('CONFIGURE'::character varying)::text, ('BUILD'::character varying)::text, ('RUN'::character varying)::text, ('MEASURE'::character varying)::text, ('CHECKPOINT'::character varying)::text, ('ANALYZE'::character varying)::text, ('EXPLAIN'::character varying)::text, ('ITERATE'::character varying)::text, ('REFLECT'::character varying)::text]))),
    CONSTRAINT workflow_nodes_order_hint_check CHECK ((order_hint >= 0))
);



CREATE TABLE public.workspace_files (
    id bigint NOT NULL,
    session_id bigint NOT NULL,
    user_id bigint NOT NULL,
    file_path character varying(1000) NOT NULL,
    minio_key character varying(500) NOT NULL,
    content_hash character varying(64) NOT NULL,
    file_size bigint DEFAULT 0 NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.workspace_files_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.workspace_files_id_seq OWNED BY public.workspace_files.id;



ALTER TABLE ONLY public.datasets ALTER COLUMN id SET DEFAULT nextval('public.datasets_id_seq'::regclass);



ALTER TABLE ONLY public.environment_templates ALTER COLUMN id SET DEFAULT nextval('public.environment_templates_id_seq'::regclass);



ALTER TABLE ONLY public.experiment_trials ALTER COLUMN id SET DEFAULT nextval('public.experiment_trials_id_seq'::regclass);



ALTER TABLE ONLY public.lab_enrollments ALTER COLUMN id SET DEFAULT nextval('public.lab_enrollments_id_seq'::regclass);



ALTER TABLE ONLY public.lab_leaderboard ALTER COLUMN id SET DEFAULT nextval('public.lab_leaderboard_id_seq'::regclass);



ALTER TABLE ONLY public.lab_runs ALTER COLUMN id SET DEFAULT nextval('public.lab_runs_id_seq'::regclass);



ALTER TABLE ONLY public.lab_runtime_task_attempts ALTER COLUMN id SET DEFAULT nextval('public.lab_runtime_task_attempts_id_seq'::regclass);



ALTER TABLE ONLY public.lab_runtime_tasks ALTER COLUMN id SET DEFAULT nextval('public.lab_runtime_tasks_id_seq'::regclass);



ALTER TABLE ONLY public.lab_section_content ALTER COLUMN id SET DEFAULT nextval('public.lab_section_content_id_seq'::regclass);



ALTER TABLE ONLY public.lab_sections ALTER COLUMN id SET DEFAULT nextval('public.lab_sections_id_seq'::regclass);



ALTER TABLE ONLY public.lab_sessions ALTER COLUMN id SET DEFAULT nextval('public.lab_sessions_id_seq'::regclass);



ALTER TABLE ONLY public.lab_submissions ALTER COLUMN id SET DEFAULT nextval('public.lab_submissions_id_seq'::regclass);



ALTER TABLE ONLY public.lab_test_cases ALTER COLUMN id SET DEFAULT nextval('public.lab_test_cases_id_seq'::regclass);



ALTER TABLE ONLY public.lab_versions ALTER COLUMN id SET DEFAULT nextval('public.lab_versions_id_seq'::regclass);



ALTER TABLE ONLY public.labs ALTER COLUMN id SET DEFAULT nextval('public.labs_id_seq'::regclass);



ALTER TABLE ONLY public.submission_test_results ALTER COLUMN id SET DEFAULT nextval('public.submission_test_results_id_seq'::regclass);



ALTER TABLE ONLY public.workflow_edges ALTER COLUMN id SET DEFAULT nextval('public.workflow_edges_id_seq'::regclass);



ALTER TABLE ONLY public.workspace_files ALTER COLUMN id SET DEFAULT nextval('public.workspace_files_id_seq'::regclass);



ALTER TABLE ONLY public.datasets
    ADD CONSTRAINT datasets_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.environment_templates
    ADD CONSTRAINT environment_templates_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.evidence_events
    ADD CONSTRAINT evidence_events_pkey PRIMARY KEY (event_id);



ALTER TABLE ONLY public.evidence_events
    ADD CONSTRAINT evidence_events_run_id_client_event_id_key UNIQUE (run_id, client_event_id);



ALTER TABLE ONLY public.evidence_events
    ADD CONSTRAINT evidence_events_run_id_seq_no_key UNIQUE (run_id, seq_no);



ALTER TABLE ONLY public.experiment_definitions
    ADD CONSTRAINT experiment_definitions_pkey PRIMARY KEY (lab_version_id);



ALTER TABLE ONLY public.experiment_trials
    ADD CONSTRAINT experiment_trials_id_run_id_key UNIQUE (id, run_id);



ALTER TABLE ONLY public.experiment_trials
    ADD CONSTRAINT experiment_trials_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.experiment_trials
    ADD CONSTRAINT experiment_trials_run_id_trial_number_key UNIQUE (run_id, trial_number);



ALTER TABLE ONLY public.experiment_variables
    ADD CONSTRAINT experiment_variables_pkey PRIMARY KEY (lab_version_id, variable_key);



ALTER TABLE ONLY public.lab_datasets
    ADD CONSTRAINT lab_datasets_pkey PRIMARY KEY (lab_id, dataset_id);



ALTER TABLE ONLY public.lab_enrollments
    ADD CONSTRAINT lab_enrollments_lab_id_user_id_key UNIQUE (lab_id, user_id);



ALTER TABLE ONLY public.lab_enrollments
    ADD CONSTRAINT lab_enrollments_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.lab_leaderboard
    ADD CONSTRAINT lab_leaderboard_lab_id_user_id_key UNIQUE (lab_id, user_id);



ALTER TABLE ONLY public.lab_leaderboard
    ADD CONSTRAINT lab_leaderboard_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.lab_runs
    ADD CONSTRAINT lab_runs_lab_version_id_user_id_idempotency_key_key UNIQUE (lab_version_id, user_id, idempotency_key);



ALTER TABLE ONLY public.lab_runs
    ADD CONSTRAINT lab_runs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.lab_runtime_task_attempts
    ADD CONSTRAINT lab_runtime_task_attempts_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.lab_runtime_tasks
    ADD CONSTRAINT lab_runtime_tasks_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.lab_section_content
    ADD CONSTRAINT lab_section_content_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.lab_sections
    ADD CONSTRAINT lab_sections_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.lab_sessions
    ADD CONSTRAINT lab_sessions_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.lab_sessions
    ADD CONSTRAINT lab_sessions_session_token_key UNIQUE (session_token);



ALTER TABLE ONLY public.lab_submissions
    ADD CONSTRAINT lab_submissions_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.lab_test_cases
    ADD CONSTRAINT lab_test_cases_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.lab_versions
    ADD CONSTRAINT lab_versions_lab_id_version_number_key UNIQUE (lab_id, version_number);



ALTER TABLE ONLY public.lab_versions
    ADD CONSTRAINT lab_versions_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.labs
    ADD CONSTRAINT labs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.submission_test_results
    ADD CONSTRAINT submission_test_results_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);



ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.workflow_edges
    ADD CONSTRAINT workflow_edges_lab_version_id_from_node_key_to_node_key_pri_key UNIQUE (lab_version_id, from_node_key, to_node_key, priority);



ALTER TABLE ONLY public.workflow_edges
    ADD CONSTRAINT workflow_edges_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.workflow_nodes
    ADD CONSTRAINT workflow_nodes_pkey PRIMARY KEY (lab_version_id, node_key);



ALTER TABLE ONLY public.workspace_files
    ADD CONSTRAINT workspace_files_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.workspace_files
    ADD CONSTRAINT workspace_files_session_id_file_path_key UNIQUE (session_id, file_path);



CREATE INDEX idx_content_section ON public.lab_section_content USING btree (section_id, order_index);



CREATE INDEX idx_enrollments_user ON public.lab_enrollments USING btree (user_id);



CREATE INDEX idx_evidence_events_replay ON public.evidence_events USING btree (run_id, seq_no);



CREATE INDEX idx_evidence_events_trial ON public.evidence_events USING btree (trial_id, seq_no) WHERE (trial_id IS NOT NULL);



CREATE INDEX idx_experiment_trials_run ON public.experiment_trials USING btree (run_id, trial_number);



CREATE INDEX idx_lab_runs_active ON public.lab_runs USING btree (lab_version_id, status) WHERE ((status)::text = 'ACTIVE'::text);



CREATE INDEX idx_lab_runs_version_user ON public.lab_runs USING btree (lab_version_id, user_id, started_at DESC);



CREATE INDEX idx_lab_versions_lab ON public.lab_versions USING btree (lab_id, version_number DESC);



CREATE UNIQUE INDEX idx_lab_versions_one_published ON public.lab_versions USING btree (lab_id) WHERE ((status)::text = 'PUBLISHED'::text);



CREATE INDEX idx_labs_creator ON public.labs USING btree (created_by);



CREATE INDEX idx_labs_status ON public.labs USING btree (status);



CREATE INDEX idx_labs_type ON public.labs USING btree (lab_type);



CREATE INDEX idx_leaderboard_score ON public.lab_leaderboard USING btree (lab_id, best_score DESC, best_runtime_ms);



CREATE INDEX idx_runtime_task_attempts_user ON public.lab_runtime_task_attempts USING btree (lab_id, user_id, checked_at DESC);



CREATE INDEX idx_runtime_tasks_lab ON public.lab_runtime_tasks USING btree (lab_id, order_index, id);



CREATE INDEX idx_sections_lab ON public.lab_sections USING btree (lab_id, order_index);



CREATE INDEX idx_sessions_status ON public.lab_sessions USING btree (status) WHERE ((status)::text = ANY (ARRAY[('RUNNING'::character varying)::text, ('PENDING'::character varying)::text, ('CREATING'::character varying)::text]));



CREATE INDEX idx_sessions_user_lab ON public.lab_sessions USING btree (user_id, lab_id);



CREATE INDEX idx_submissions_lab_user ON public.lab_submissions USING btree (lab_id, user_id);



CREATE INDEX idx_submissions_status ON public.lab_submissions USING btree (status);



CREATE INDEX idx_test_cases_lab ON public.lab_test_cases USING btree (lab_id, order_index);



CREATE INDEX idx_test_results_sub ON public.submission_test_results USING btree (submission_id);



CREATE INDEX idx_workspace_hash ON public.workspace_files USING btree (content_hash);



ALTER TABLE ONLY public.datasets
    ADD CONSTRAINT datasets_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.environment_templates
    ADD CONSTRAINT environment_templates_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.evidence_events
    ADD CONSTRAINT evidence_events_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.users(id);



ALTER TABLE ONLY public.evidence_events
    ADD CONSTRAINT evidence_events_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.lab_runs(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.evidence_events
    ADD CONSTRAINT evidence_events_trial_id_run_id_fkey FOREIGN KEY (trial_id, run_id) REFERENCES public.experiment_trials(id, run_id);



ALTER TABLE ONLY public.experiment_definitions
    ADD CONSTRAINT experiment_definitions_lab_version_id_fkey FOREIGN KEY (lab_version_id) REFERENCES public.lab_versions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.experiment_trials
    ADD CONSTRAINT experiment_trials_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.lab_runs(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.experiment_variables
    ADD CONSTRAINT experiment_variables_lab_version_id_fkey FOREIGN KEY (lab_version_id) REFERENCES public.lab_versions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.lab_datasets
    ADD CONSTRAINT lab_datasets_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES public.datasets(id);



ALTER TABLE ONLY public.lab_datasets
    ADD CONSTRAINT lab_datasets_lab_id_fkey FOREIGN KEY (lab_id) REFERENCES public.labs(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.lab_enrollments
    ADD CONSTRAINT lab_enrollments_lab_id_fkey FOREIGN KEY (lab_id) REFERENCES public.labs(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.lab_enrollments
    ADD CONSTRAINT lab_enrollments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);



ALTER TABLE ONLY public.lab_leaderboard
    ADD CONSTRAINT lab_leaderboard_best_submission_id_fkey FOREIGN KEY (best_submission_id) REFERENCES public.lab_submissions(id);



ALTER TABLE ONLY public.lab_leaderboard
    ADD CONSTRAINT lab_leaderboard_lab_id_fkey FOREIGN KEY (lab_id) REFERENCES public.labs(id);



ALTER TABLE ONLY public.lab_leaderboard
    ADD CONSTRAINT lab_leaderboard_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);



ALTER TABLE ONLY public.lab_runs
    ADD CONSTRAINT lab_runs_lab_version_id_fkey FOREIGN KEY (lab_version_id) REFERENCES public.lab_versions(id);



ALTER TABLE ONLY public.lab_runs
    ADD CONSTRAINT lab_runs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);



ALTER TABLE ONLY public.lab_runtime_task_attempts
    ADD CONSTRAINT lab_runtime_task_attempts_lab_id_fkey FOREIGN KEY (lab_id) REFERENCES public.labs(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.lab_runtime_task_attempts
    ADD CONSTRAINT lab_runtime_task_attempts_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.lab_runtime_tasks(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.lab_runtime_task_attempts
    ADD CONSTRAINT lab_runtime_task_attempts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);



ALTER TABLE ONLY public.lab_runtime_tasks
    ADD CONSTRAINT lab_runtime_tasks_lab_id_fkey FOREIGN KEY (lab_id) REFERENCES public.labs(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.lab_section_content
    ADD CONSTRAINT lab_section_content_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.lab_section_content
    ADD CONSTRAINT lab_section_content_section_id_fkey FOREIGN KEY (section_id) REFERENCES public.lab_sections(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.lab_sections
    ADD CONSTRAINT lab_sections_lab_id_fkey FOREIGN KEY (lab_id) REFERENCES public.labs(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.lab_sessions
    ADD CONSTRAINT lab_sessions_lab_id_fkey FOREIGN KEY (lab_id) REFERENCES public.labs(id);



ALTER TABLE ONLY public.lab_sessions
    ADD CONSTRAINT lab_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);



ALTER TABLE ONLY public.lab_submissions
    ADD CONSTRAINT lab_submissions_lab_id_fkey FOREIGN KEY (lab_id) REFERENCES public.labs(id);



ALTER TABLE ONLY public.lab_submissions
    ADD CONSTRAINT lab_submissions_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.lab_sessions(id);



ALTER TABLE ONLY public.lab_submissions
    ADD CONSTRAINT lab_submissions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);



ALTER TABLE ONLY public.lab_test_cases
    ADD CONSTRAINT lab_test_cases_lab_id_fkey FOREIGN KEY (lab_id) REFERENCES public.labs(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.lab_versions
    ADD CONSTRAINT lab_versions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.lab_versions
    ADD CONSTRAINT lab_versions_lab_id_fkey FOREIGN KEY (lab_id) REFERENCES public.labs(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.labs
    ADD CONSTRAINT labs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.labs
    ADD CONSTRAINT labs_environment_template_id_fkey FOREIGN KEY (environment_template_id) REFERENCES public.environment_templates(id);



ALTER TABLE ONLY public.submission_test_results
    ADD CONSTRAINT submission_test_results_submission_id_fkey FOREIGN KEY (submission_id) REFERENCES public.lab_submissions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.submission_test_results
    ADD CONSTRAINT submission_test_results_test_case_id_fkey FOREIGN KEY (test_case_id) REFERENCES public.lab_test_cases(id);



ALTER TABLE ONLY public.workflow_edges
    ADD CONSTRAINT workflow_edges_lab_version_id_fkey FOREIGN KEY (lab_version_id) REFERENCES public.lab_versions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.workflow_edges
    ADD CONSTRAINT workflow_edges_lab_version_id_from_node_key_fkey FOREIGN KEY (lab_version_id, from_node_key) REFERENCES public.workflow_nodes(lab_version_id, node_key) ON DELETE CASCADE;



ALTER TABLE ONLY public.workflow_edges
    ADD CONSTRAINT workflow_edges_lab_version_id_to_node_key_fkey FOREIGN KEY (lab_version_id, to_node_key) REFERENCES public.workflow_nodes(lab_version_id, node_key) ON DELETE CASCADE;



ALTER TABLE ONLY public.workflow_nodes
    ADD CONSTRAINT workflow_nodes_lab_version_id_fkey FOREIGN KEY (lab_version_id) REFERENCES public.lab_versions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.workspace_files
    ADD CONSTRAINT workspace_files_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.lab_sessions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.workspace_files
    ADD CONSTRAINT workspace_files_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);

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










































































SELECT pg_catalog.setval('public.datasets_id_seq', 1, false);



SELECT pg_catalog.setval('public.environment_templates_id_seq', 1, false);



SELECT pg_catalog.setval('public.experiment_trials_id_seq', 1, false);



SELECT pg_catalog.setval('public.lab_enrollments_id_seq', 1, false);



SELECT pg_catalog.setval('public.lab_leaderboard_id_seq', 1, false);



SELECT pg_catalog.setval('public.lab_runs_id_seq', 1, false);



SELECT pg_catalog.setval('public.lab_runtime_task_attempts_id_seq', 1, false);



SELECT pg_catalog.setval('public.lab_runtime_tasks_id_seq', 1, false);



SELECT pg_catalog.setval('public.lab_section_content_id_seq', 1, false);



SELECT pg_catalog.setval('public.lab_sections_id_seq', 1, false);



SELECT pg_catalog.setval('public.lab_sessions_id_seq', 1, false);



SELECT pg_catalog.setval('public.lab_submissions_id_seq', 1, false);



SELECT pg_catalog.setval('public.lab_test_cases_id_seq', 1, false);



SELECT pg_catalog.setval('public.lab_versions_id_seq', 1, false);



SELECT pg_catalog.setval('public.labs_id_seq', 1, false);



SELECT pg_catalog.setval('public.submission_test_results_id_seq', 1, false);



SELECT pg_catalog.setval('public.workflow_edges_id_seq', 1, false);



SELECT pg_catalog.setval('public.workspace_files_id_seq', 1, false);

-- Record the historical identities covered by this fresh baseline.
CREATE TABLE public.lab_schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());
INSERT INTO public.lab_schema_migrations (version) VALUES
('V001__lab_core.sql'),
('V002__submissions.sql'),
('V003__virtual_stem_foundation.sql'),
('V004__chemistry_lab_support.sql'),
('V005__runtime_tasks.sql'),
('V006__grading_compile_status.sql');
