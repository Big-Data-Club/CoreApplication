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


CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;


CREATE TABLE public.chat_attachments (
    id character varying(64) NOT NULL,
    message_id bigint NOT NULL,
    object_key character varying(512) NOT NULL,
    file_name character varying(255) NOT NULL,
    mime_type character varying(150) NOT NULL,
    size_bytes bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chat_attachments_size_bytes_check CHECK (((size_bytes > 0) AND (size_bytes <= 20971520)))
);



CREATE TABLE public.chat_channel_roles (
    channel_id bigint NOT NULL,
    role_name character varying(80) NOT NULL,
    can_read boolean DEFAULT true NOT NULL,
    can_write boolean DEFAULT true NOT NULL
);



CREATE TABLE public.chat_channel_users (
    channel_id bigint NOT NULL,
    user_id bigint NOT NULL
);



CREATE TABLE public.chat_channels (
    id bigint NOT NULL,
    slug character varying(80) NOT NULL,
    name character varying(120) NOT NULL,
    description text,
    is_private boolean DEFAULT false NOT NULL,
    created_by bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_dm boolean DEFAULT false NOT NULL
);



CREATE SEQUENCE public.chat_channels_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.chat_channels_id_seq OWNED BY public.chat_channels.id;



CREATE TABLE public.chat_messages (
    id bigint NOT NULL,
    channel_id bigint NOT NULL,
    sender_id bigint NOT NULL,
    body text NOT NULL,
    is_deleted boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    parent_id bigint,
    is_edited boolean DEFAULT false NOT NULL,
    CONSTRAINT chat_messages_body_length_check CHECK ((char_length(body) <= 4000))
);



CREATE SEQUENCE public.chat_messages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.chat_messages_id_seq OWNED BY public.chat_messages.id;



CREATE TABLE public.users (
    id bigint NOT NULL,
    email character varying(255) NOT NULL,
    full_name character varying(255) DEFAULT ''::character varying NOT NULL,
    profile_picture character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);



ALTER TABLE ONLY public.chat_channels ALTER COLUMN id SET DEFAULT nextval('public.chat_channels_id_seq'::regclass);



ALTER TABLE ONLY public.chat_messages ALTER COLUMN id SET DEFAULT nextval('public.chat_messages_id_seq'::regclass);



ALTER TABLE ONLY public.chat_attachments
    ADD CONSTRAINT chat_attachments_object_key_key UNIQUE (object_key);



ALTER TABLE ONLY public.chat_attachments
    ADD CONSTRAINT chat_attachments_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.chat_channel_roles
    ADD CONSTRAINT chat_channel_roles_pkey PRIMARY KEY (channel_id, role_name);



ALTER TABLE ONLY public.chat_channel_users
    ADD CONSTRAINT chat_channel_users_pkey PRIMARY KEY (channel_id, user_id);



ALTER TABLE ONLY public.chat_channels
    ADD CONSTRAINT chat_channels_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.chat_channels
    ADD CONSTRAINT chat_channels_slug_key UNIQUE (slug);



ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);



ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);



CREATE INDEX idx_channel_roles_channel ON public.chat_channel_roles USING btree (channel_id);



CREATE INDEX idx_channel_users_user ON public.chat_channel_users USING btree (user_id);



CREATE INDEX idx_channels_is_dm ON public.chat_channels USING btree (is_dm);



CREATE INDEX idx_chat_attachments_message ON public.chat_attachments USING btree (message_id);



CREATE INDEX idx_chat_channel_users_user_channel ON public.chat_channel_users USING btree (user_id, channel_id);



CREATE INDEX idx_messages_channel_all ON public.chat_messages USING btree (channel_id, id DESC);



CREATE INDEX idx_messages_channel_created ON public.chat_messages USING btree (channel_id, created_at DESC) WHERE (is_deleted = false);



CREATE INDEX idx_messages_parent_id ON public.chat_messages USING btree (parent_id) WHERE (parent_id IS NOT NULL);



CREATE INDEX idx_users_email ON public.users USING btree (email);



CREATE TRIGGER trg_channels_updated_at BEFORE UPDATE ON public.chat_channels FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER trg_messages_updated_at BEFORE UPDATE ON public.chat_messages FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



ALTER TABLE ONLY public.chat_attachments
    ADD CONSTRAINT chat_attachments_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.chat_messages(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.chat_channel_roles
    ADD CONSTRAINT chat_channel_roles_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES public.chat_channels(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.chat_channel_users
    ADD CONSTRAINT chat_channel_users_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES public.chat_channels(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.chat_channel_users
    ADD CONSTRAINT chat_channel_users_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.chat_channels
    ADD CONSTRAINT chat_channels_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES public.chat_channels(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.chat_messages(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_sender_id_fkey FOREIGN KEY (sender_id) REFERENCES public.users(id);

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




















SELECT pg_catalog.setval('public.chat_channels_id_seq', 1, false);



SELECT pg_catalog.setval('public.chat_messages_id_seq', 1, false);

-- Record the historical identities covered by this fresh baseline.
CREATE TABLE public.schema_migrations (version VARCHAR(255) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());
INSERT INTO public.schema_migrations (version) VALUES
('V001__chat_schema.sql'),
('V002__dm_support.sql'),
('V003__seed_existing_channels.sql'),
('V004__message_replies_and_edits.sql'),
('V005__chat_attachments.sql'),
('V006__chat_history_and_membership_indexes.sql');
