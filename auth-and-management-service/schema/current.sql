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


CREATE TABLE public.farm_score_receipts (
    event_id uuid NOT NULL,
    harvest_id uuid NOT NULL,
    user_id bigint NOT NULL,
    delta integer NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    applied_at timestamp with time zone NOT NULL,
    CONSTRAINT farm_score_receipts_delta_check CHECK ((delta = 5))
);



CREATE TABLE public.tenant_sites (
    org_id bigint NOT NULL,
    revision bigint DEFAULT 0 NOT NULL,
    draft text NOT NULL,
    published text,
    published_at timestamp with time zone
);



ALTER TABLE ONLY public.farm_score_receipts
    ADD CONSTRAINT farm_score_receipts_harvest_id_key UNIQUE (harvest_id);



ALTER TABLE ONLY public.farm_score_receipts
    ADD CONSTRAINT farm_score_receipts_pkey PRIMARY KEY (event_id);



ALTER TABLE ONLY public.tenant_sites
    ADD CONSTRAINT tenant_sites_pkey PRIMARY KEY (org_id);



CREATE INDEX farm_score_receipts_user_idx ON public.farm_score_receipts USING btree (user_id);



ALTER TABLE ONLY public.tenant_sites
    ADD CONSTRAINT tenant_sites_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;

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
