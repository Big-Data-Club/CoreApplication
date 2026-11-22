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


CREATE TABLE public.attachment_bindings (
    attachment_id uuid NOT NULL,
    page_id uuid NOT NULL
);



CREATE TABLE public.attachments (
    id uuid NOT NULL,
    uploaded_by text NOT NULL,
    filename text NOT NULL,
    mime text NOT NULL,
    content bytea NOT NULL,
    size integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT attachments_size_check CHECK (((size > 0) AND (size <= 10485760)))
);



CREATE TABLE public.block_activity (
    page_id uuid NOT NULL,
    block_id text NOT NULL,
    actor_id text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.comments (
    id uuid NOT NULL,
    page_id uuid NOT NULL,
    block_id text,
    parent_id uuid,
    author_id text NOT NULL,
    body text NOT NULL,
    resolved boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT comments_body_check CHECK (((length(body) >= 1) AND (length(body) <= 10000)))
);



CREATE TABLE public.database_schemas (
    page_id uuid NOT NULL,
    fields jsonb DEFAULT '[]'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL
);



CREATE TABLE public.database_views (
    id uuid NOT NULL,
    page_id uuid NOT NULL,
    owner_id text,
    name text NOT NULL,
    type text NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT database_views_type_check CHECK ((type = ANY (ARRAY['table'::text, 'board'::text, 'calendar'::text, 'list'::text, 'gallery'::text, 'timeline'::text])))
);



CREATE TABLE public.document_operations (
    page_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    generation integer NOT NULL,
    revision bigint NOT NULL,
    author_id text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.invitations (
    id uuid NOT NULL,
    space_id uuid,
    page_id uuid,
    email text NOT NULL,
    role text NOT NULL,
    created_by text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone DEFAULT (now() + '7 days'::interval) NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    CONSTRAINT invitations_check CHECK (((space_id IS NULL) <> (page_id IS NULL))),
    CONSTRAINT invitations_role_check CHECK ((role = ANY (ARRAY['viewer'::text, 'commenter'::text, 'editor'::text, 'manager'::text]))),
    CONSTRAINT invitations_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'accepted'::text, 'declined'::text, 'cancelled'::text])))
);



CREATE TABLE public.legacy_note_imports (
    user_id text NOT NULL,
    note_id text NOT NULL,
    page_id uuid NOT NULL,
    space_id uuid NOT NULL
);



CREATE TABLE public.page_documents (
    page_id uuid NOT NULL,
    state bytea DEFAULT '\x'::bytea NOT NULL,
    revision bigint DEFAULT 0 NOT NULL,
    generation integer DEFAULT 1 NOT NULL,
    search_text text DEFAULT ''::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.page_grants (
    page_id uuid NOT NULL,
    user_id text NOT NULL,
    role text NOT NULL,
    CONSTRAINT page_grants_role_check CHECK ((role = ANY (ARRAY['viewer'::text, 'commenter'::text, 'editor'::text, 'manager'::text])))
);



CREATE TABLE public.page_links (
    source_id uuid NOT NULL,
    target_id uuid NOT NULL
);



CREATE TABLE public.page_preferences (
    page_id uuid NOT NULL,
    user_id text NOT NULL,
    favorite boolean DEFAULT false NOT NULL,
    opened_at timestamp with time zone DEFAULT now()
);



CREATE TABLE public.page_versions (
    id uuid NOT NULL,
    page_id uuid NOT NULL,
    author_id text NOT NULL,
    title text NOT NULL,
    label text NOT NULL,
    state bytea NOT NULL,
    properties jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.page_view_preferences (
    page_id uuid NOT NULL,
    user_id text NOT NULL,
    show_name boolean DEFAULT false NOT NULL
);



CREATE TABLE public.page_visits (
    id bigint NOT NULL,
    page_id uuid NOT NULL,
    user_id text NOT NULL,
    viewed_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.page_visits_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.page_visits_id_seq OWNED BY public.page_visits.id;



CREATE TABLE public.pages (
    id uuid NOT NULL,
    space_id uuid NOT NULL,
    parent_id uuid,
    title text DEFAULT 'Trang không tiêu đề'::text NOT NULL,
    icon text DEFAULT ''::text NOT NULL,
    cover text DEFAULT ''::text NOT NULL,
    full_width boolean DEFAULT false NOT NULL,
    kind text DEFAULT 'page'::text NOT NULL,
    properties jsonb DEFAULT '{}'::jsonb NOT NULL,
    sources jsonb DEFAULT '[]'::jsonb NOT NULL,
    initial_markdown text DEFAULT ''::text NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    sort_order double precision DEFAULT 0 NOT NULL,
    archived_batch uuid,
    archived_at timestamp with time zone,
    created_by text NOT NULL,
    updated_by text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    field_id uuid,
    cover_image_id uuid,
    CONSTRAINT pages_check CHECK (((parent_id IS NULL) OR (parent_id <> id))),
    CONSTRAINT pages_kind_check CHECK ((kind = ANY (ARRAY['page'::text, 'database'::text, 'record'::text]))),
    CONSTRAINT pages_title_check CHECK (((length(title) >= 1) AND (length(title) <= 300)))
);



CREATE TABLE public.space_members (
    space_id uuid NOT NULL,
    user_id text NOT NULL,
    role text NOT NULL,
    CONSTRAINT space_members_role_check CHECK ((role = ANY (ARRAY['viewer'::text, 'commenter'::text, 'editor'::text, 'manager'::text, 'owner'::text])))
);



CREATE TABLE public.spaces (
    id uuid NOT NULL,
    title text NOT NULL,
    kind text NOT NULL,
    owner_id text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT spaces_kind_check CHECK ((kind = ANY (ARRAY['personal'::text, 'team'::text]))),
    CONSTRAINT spaces_title_check CHECK (((length(title) >= 1) AND (length(title) <= 120)))
);



CREATE TABLE public.websocket_tickets (
    digest text NOT NULL,
    page_id uuid NOT NULL,
    user_id text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    identity_expires_at timestamp with time zone DEFAULT (now() + '01:00:00'::interval) NOT NULL
);



CREATE TABLE public.workspace_activity (
    id uuid NOT NULL,
    space_id uuid NOT NULL,
    page_id uuid,
    actor_id text NOT NULL,
    action text NOT NULL,
    detail jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.workspace_fields (
    id uuid NOT NULL,
    space_id uuid NOT NULL,
    title text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    icon text DEFAULT 'book'::text NOT NULL,
    color text DEFAULT 'violet'::text NOT NULL,
    tags jsonb DEFAULT '[]'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    archived_at timestamp with time zone,
    archived_batch uuid,
    created_by text NOT NULL,
    updated_by text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT workspace_fields_description_check CHECK ((length(description) <= 280)),
    CONSTRAINT workspace_fields_title_check CHECK (((length(title) >= 1) AND (length(title) <= 120)))
);



CREATE TABLE public.workspace_notifications (
    id uuid NOT NULL,
    user_id text NOT NULL,
    page_id uuid,
    kind text NOT NULL,
    read_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.workspace_users (
    id text NOT NULL,
    email text NOT NULL,
    name text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);



ALTER TABLE ONLY public.page_visits ALTER COLUMN id SET DEFAULT nextval('public.page_visits_id_seq'::regclass);



ALTER TABLE ONLY public.attachment_bindings
    ADD CONSTRAINT attachment_bindings_pkey PRIMARY KEY (attachment_id, page_id);



ALTER TABLE ONLY public.attachments
    ADD CONSTRAINT attachments_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.block_activity
    ADD CONSTRAINT block_activity_pkey PRIMARY KEY (page_id, block_id);



ALTER TABLE ONLY public.comments
    ADD CONSTRAINT comments_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.database_schemas
    ADD CONSTRAINT database_schemas_pkey PRIMARY KEY (page_id);



ALTER TABLE ONLY public.database_views
    ADD CONSTRAINT database_views_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.document_operations
    ADD CONSTRAINT document_operations_pkey PRIMARY KEY (page_id, operation_id);



ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT invitations_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.legacy_note_imports
    ADD CONSTRAINT legacy_note_imports_pkey PRIMARY KEY (user_id, note_id, space_id);



ALTER TABLE ONLY public.page_documents
    ADD CONSTRAINT page_documents_pkey PRIMARY KEY (page_id);



ALTER TABLE ONLY public.page_grants
    ADD CONSTRAINT page_grants_pkey PRIMARY KEY (page_id, user_id);



ALTER TABLE ONLY public.page_links
    ADD CONSTRAINT page_links_pkey PRIMARY KEY (source_id, target_id);



ALTER TABLE ONLY public.page_preferences
    ADD CONSTRAINT page_preferences_pkey PRIMARY KEY (page_id, user_id);



ALTER TABLE ONLY public.page_versions
    ADD CONSTRAINT page_versions_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.page_view_preferences
    ADD CONSTRAINT page_view_preferences_pkey PRIMARY KEY (page_id, user_id);



ALTER TABLE ONLY public.page_visits
    ADD CONSTRAINT page_visits_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_field_parent_unique UNIQUE (id, space_id, field_id);



ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_id_space_id_key UNIQUE (id, space_id);



ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.space_members
    ADD CONSTRAINT space_members_pkey PRIMARY KEY (space_id, user_id);



ALTER TABLE ONLY public.spaces
    ADD CONSTRAINT spaces_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.websocket_tickets
    ADD CONSTRAINT websocket_tickets_pkey PRIMARY KEY (digest);



ALTER TABLE ONLY public.workspace_activity
    ADD CONSTRAINT workspace_activity_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.workspace_fields
    ADD CONSTRAINT workspace_fields_id_space_id_key UNIQUE (id, space_id);



ALTER TABLE ONLY public.workspace_fields
    ADD CONSTRAINT workspace_fields_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.workspace_notifications
    ADD CONSTRAINT workspace_notifications_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.workspace_users
    ADD CONSTRAINT workspace_users_email_key UNIQUE (email);



ALTER TABLE ONLY public.workspace_users
    ADD CONSTRAINT workspace_users_pkey PRIMARY KEY (id);



CREATE INDEX comments_page ON public.comments USING btree (page_id, created_at);



CREATE INDEX documents_search ON public.page_documents USING gin (to_tsvector('simple'::regconfig, search_text));



CREATE UNIQUE INDEX invites_pending_page ON public.invitations USING btree (page_id, email) WHERE (status = 'pending'::text);



CREATE UNIQUE INDEX invites_pending_space ON public.invitations USING btree (space_id, email) WHERE (status = 'pending'::text);



CREATE INDEX page_links_target_idx ON public.page_links USING btree (target_id);



CREATE INDEX page_preferences_user_recent ON public.page_preferences USING btree (user_id, opened_at DESC, page_id) WHERE (opened_at IS NOT NULL);



CREATE INDEX page_versions_retention ON public.page_versions USING btree (page_id, created_at DESC, id DESC);



CREATE INDEX page_visits_daily ON public.page_visits USING btree (page_id, viewed_at DESC);



CREATE INDEX page_visits_reader ON public.page_visits USING btree (page_id, user_id, viewed_at DESC);



CREATE INDEX pages_field_tree ON public.pages USING btree (field_id, parent_id, sort_order) WHERE (archived_at IS NULL);



CREATE INDEX pages_library_updated ON public.pages USING btree (updated_at DESC, id) WHERE (archived_at IS NULL);



CREATE INDEX pages_records ON public.pages USING btree (parent_id, updated_at DESC) WHERE ((kind = 'record'::text) AND (archived_at IS NULL));



CREATE INDEX pages_tree ON public.pages USING btree (space_id, parent_id, sort_order) WHERE (archived_at IS NULL);



CREATE UNIQUE INDEX spaces_one_personal ON public.spaces USING btree (owner_id) WHERE (kind = 'personal'::text);



CREATE INDEX versions_page ON public.page_versions USING btree (page_id, created_at DESC);



CREATE INDEX workspace_fields_space ON public.workspace_fields USING btree (space_id, created_at);



ALTER TABLE ONLY public.attachment_bindings
    ADD CONSTRAINT attachment_bindings_attachment_id_fkey FOREIGN KEY (attachment_id) REFERENCES public.attachments(id);



ALTER TABLE ONLY public.attachment_bindings
    ADD CONSTRAINT attachment_bindings_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id);



ALTER TABLE ONLY public.attachments
    ADD CONSTRAINT attachments_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.block_activity
    ADD CONSTRAINT block_activity_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.block_activity
    ADD CONSTRAINT block_activity_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.comments
    ADD CONSTRAINT comments_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.comments
    ADD CONSTRAINT comments_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id);



ALTER TABLE ONLY public.comments
    ADD CONSTRAINT comments_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.comments(id);



ALTER TABLE ONLY public.database_schemas
    ADD CONSTRAINT database_schemas_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id);



ALTER TABLE ONLY public.database_views
    ADD CONSTRAINT database_views_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.database_views
    ADD CONSTRAINT database_views_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id);



ALTER TABLE ONLY public.document_operations
    ADD CONSTRAINT document_operations_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.document_operations
    ADD CONSTRAINT document_operations_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT invitations_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT invitations_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT invitations_space_id_fkey FOREIGN KEY (space_id) REFERENCES public.spaces(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.legacy_note_imports
    ADD CONSTRAINT legacy_note_imports_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id);



ALTER TABLE ONLY public.legacy_note_imports
    ADD CONSTRAINT legacy_note_imports_space_id_fkey FOREIGN KEY (space_id) REFERENCES public.spaces(id);



ALTER TABLE ONLY public.legacy_note_imports
    ADD CONSTRAINT legacy_note_imports_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.page_documents
    ADD CONSTRAINT page_documents_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.page_grants
    ADD CONSTRAINT page_grants_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.page_grants
    ADD CONSTRAINT page_grants_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.page_links
    ADD CONSTRAINT page_links_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.pages(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.page_preferences
    ADD CONSTRAINT page_preferences_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.page_preferences
    ADD CONSTRAINT page_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.page_versions
    ADD CONSTRAINT page_versions_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.page_versions
    ADD CONSTRAINT page_versions_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id);



ALTER TABLE ONLY public.page_view_preferences
    ADD CONSTRAINT page_view_preferences_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.page_view_preferences
    ADD CONSTRAINT page_view_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.page_visits
    ADD CONSTRAINT page_visits_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.page_visits
    ADD CONSTRAINT page_visits_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_cover_image_id_fkey FOREIGN KEY (cover_image_id) REFERENCES public.attachments(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_field_parent_fk FOREIGN KEY (parent_id, space_id, field_id) REFERENCES public.pages(id, space_id, field_id) DEFERRABLE INITIALLY DEFERRED;



ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_field_space_fk FOREIGN KEY (field_id, space_id) REFERENCES public.workspace_fields(id, space_id);



ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_parent_id_space_id_fkey FOREIGN KEY (parent_id, space_id) REFERENCES public.pages(id, space_id);



ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_space_id_fkey FOREIGN KEY (space_id) REFERENCES public.spaces(id);



ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.space_members
    ADD CONSTRAINT space_members_space_id_fkey FOREIGN KEY (space_id) REFERENCES public.spaces(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.space_members
    ADD CONSTRAINT space_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.spaces
    ADD CONSTRAINT spaces_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.websocket_tickets
    ADD CONSTRAINT websocket_tickets_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id);



ALTER TABLE ONLY public.websocket_tickets
    ADD CONSTRAINT websocket_tickets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.workspace_activity
    ADD CONSTRAINT workspace_activity_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.workspace_activity
    ADD CONSTRAINT workspace_activity_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id);



ALTER TABLE ONLY public.workspace_activity
    ADD CONSTRAINT workspace_activity_space_id_fkey FOREIGN KEY (space_id) REFERENCES public.spaces(id);



ALTER TABLE ONLY public.workspace_fields
    ADD CONSTRAINT workspace_fields_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.workspace_fields
    ADD CONSTRAINT workspace_fields_space_id_fkey FOREIGN KEY (space_id) REFERENCES public.spaces(id);



ALTER TABLE ONLY public.workspace_fields
    ADD CONSTRAINT workspace_fields_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.workspace_users(id);



ALTER TABLE ONLY public.workspace_notifications
    ADD CONSTRAINT workspace_notifications_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id);



ALTER TABLE ONLY public.workspace_notifications
    ADD CONSTRAINT workspace_notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.workspace_users(id);

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










































































SELECT pg_catalog.setval('public.page_visits_id_seq', 1, false);

-- Record the historical identities covered by this fresh baseline.
CREATE TABLE public.workspace_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());
INSERT INTO public.workspace_migrations (name) VALUES
('001_workspace.sql'),
('002_ticket_session_expiry.sql'),
('003_page_links.sql'),
('004_user_fields.sql'),
('005_block_activity.sql'),
('006_page_analytics.sql'),
('007_page_cover_image.sql'),
('008_library.sql'),
('009_bounded_versions.sql'),
('010_notebook_destinations.sql');
