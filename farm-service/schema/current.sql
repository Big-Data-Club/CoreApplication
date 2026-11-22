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


CREATE TABLE public.economy_ledger (
    id uuid NOT NULL,
    farm_id uuid NOT NULL,
    event_type text NOT NULL,
    kind text NOT NULL,
    quantity integer DEFAULT 0 NOT NULL,
    coins_delta integer DEFAULT 0 NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.entity_runtime (
    entity_id uuid NOT NULL,
    last_tick timestamp with time zone DEFAULT now() NOT NULL,
    work_seconds integer DEFAULT 0 NOT NULL,
    work_remainder integer DEFAULT 0 NOT NULL,
    hunger_seconds integer DEFAULT 43200 NOT NULL,
    starvation_seconds integer DEFAULT 0 NOT NULL,
    water_seconds integer DEFAULT 0 NOT NULL,
    health integer DEFAULT 100 NOT NULL,
    sick boolean DEFAULT false NOT NULL,
    yield_ready integer DEFAULT 0 NOT NULL,
    oxygen integer DEFAULT 100 NOT NULL,
    oxygen_age_seconds integer DEFAULT 0 NOT NULL,
    build_until timestamp with time zone,
    last_petted timestamp with time zone DEFAULT '2000-01-01 00:00:00+00'::timestamp with time zone NOT NULL,
    regrow_until timestamp with time zone,
    CONSTRAINT entity_runtime_health_check CHECK (((health >= 0) AND (health <= 100))),
    CONSTRAINT entity_runtime_oxygen_check CHECK (((oxygen >= 0) AND (oxygen <= 100)))
);



CREATE TABLE public.farm_answers (
    challenge_id uuid NOT NULL,
    user_id bigint NOT NULL,
    result jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.farm_economy (
    farm_id uuid NOT NULL,
    last_tick timestamp with time zone DEFAULT now() NOT NULL,
    hunger_seconds integer DEFAULT 43200 NOT NULL,
    insects integer DEFAULT 1 NOT NULL,
    insect_last_spawn timestamp with time zone DEFAULT now() NOT NULL,
    last_catch timestamp with time zone DEFAULT '2000-01-01 00:00:00+00'::timestamp with time zone NOT NULL,
    tutorial_step integer DEFAULT 0 NOT NULL,
    insect_seeded boolean DEFAULT false NOT NULL,
    care_rules_version integer DEFAULT 1 NOT NULL,
    CONSTRAINT farm_economy_hunger_seconds_check CHECK ((hunger_seconds >= 0)),
    CONSTRAINT farm_economy_insects_check CHECK (((insects >= 0) AND (insects <= 4)))
);



CREATE TABLE public.farm_inventory (
    farm_id uuid NOT NULL,
    kind text NOT NULL,
    quantity integer DEFAULT 0 NOT NULL,
    CONSTRAINT farm_inventory_quantity_check CHECK ((quantity >= 0))
);



CREATE TABLE public.farm_outbox (
    event_id uuid NOT NULL,
    user_id bigint NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    published_at timestamp with time zone
);



CREATE TABLE public.farm_states (
    user_id bigint NOT NULL,
    state jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT farm_states_user_id_check CHECK ((user_id > 0))
);



CREATE TABLE public.farm_wild_insects (
    id uuid NOT NULL,
    farm_id uuid NOT NULL,
    species text NOT NULL,
    x smallint NOT NULL,
    y smallint NOT NULL,
    spawned_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    CONSTRAINT farm_wild_insects_species_check CHECK ((species = ANY (ARRAY['ladybug'::text, 'grasshopper'::text, 'butterfly'::text, 'dragonfly'::text]))),
    CONSTRAINT farm_wild_insects_x_check CHECK (((x >= 0) AND (x <= 19))),
    CONSTRAINT farm_wild_insects_y_check CHECK (((y >= 0) AND (y <= 13)))
);



CREATE TABLE public.game_harvest_receipts (
    challenge_id uuid NOT NULL,
    user_id bigint NOT NULL,
    entity_id uuid NOT NULL,
    action text NOT NULL
);



CREATE TABLE public.game_learning (
    user_id bigint NOT NULL,
    entity_id uuid NOT NULL,
    action text NOT NULL,
    state jsonb NOT NULL
);



CREATE TABLE public.game_learning_outbox (
    challenge_id uuid NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    delivered_at timestamp with time zone,
    next_attempt_at timestamp with time zone DEFAULT now() NOT NULL,
    attempts integer DEFAULT 0 NOT NULL
);



CREATE TABLE public.virtual_farms (
    id uuid NOT NULL,
    owner_id bigint NOT NULL,
    name character varying(100) NOT NULL,
    coins integer DEFAULT 900 NOT NULL,
    xp integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT virtual_farms_coins_check CHECK ((coins >= 0)),
    CONSTRAINT virtual_farms_owner_id_check CHECK ((owner_id > 0))
);



CREATE TABLE public.world_entities (
    id uuid NOT NULL,
    farm_id uuid NOT NULL,
    category text NOT NULL,
    kind text NOT NULL,
    x integer NOT NULL,
    y integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT world_entities_category_check CHECK ((category = ANY (ARRAY['CROP'::text, 'ANIMAL'::text, 'STRUCTURE'::text, 'DECOR'::text]))),
    CONSTRAINT world_entities_x_check CHECK (((x >= 0) AND (x <= 19))),
    CONSTRAINT world_entities_y_check CHECK (((y >= 0) AND (y <= 13)))
);



ALTER TABLE ONLY public.economy_ledger
    ADD CONSTRAINT economy_ledger_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.entity_runtime
    ADD CONSTRAINT entity_runtime_pkey PRIMARY KEY (entity_id);



ALTER TABLE ONLY public.farm_answers
    ADD CONSTRAINT farm_answers_pkey PRIMARY KEY (challenge_id);



ALTER TABLE ONLY public.farm_economy
    ADD CONSTRAINT farm_economy_pkey PRIMARY KEY (farm_id);



ALTER TABLE ONLY public.farm_inventory
    ADD CONSTRAINT farm_inventory_pkey PRIMARY KEY (farm_id, kind);



ALTER TABLE ONLY public.farm_outbox
    ADD CONSTRAINT farm_outbox_pkey PRIMARY KEY (event_id);



ALTER TABLE ONLY public.farm_states
    ADD CONSTRAINT farm_states_pkey PRIMARY KEY (user_id);



ALTER TABLE ONLY public.farm_wild_insects
    ADD CONSTRAINT farm_wild_insects_farm_id_x_y_key UNIQUE (farm_id, x, y);



ALTER TABLE ONLY public.farm_wild_insects
    ADD CONSTRAINT farm_wild_insects_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.game_harvest_receipts
    ADD CONSTRAINT game_harvest_receipts_pkey PRIMARY KEY (challenge_id);



ALTER TABLE ONLY public.game_learning_outbox
    ADD CONSTRAINT game_learning_outbox_pkey PRIMARY KEY (challenge_id);



ALTER TABLE ONLY public.game_learning
    ADD CONSTRAINT game_learning_pkey PRIMARY KEY (user_id, entity_id, action);



ALTER TABLE ONLY public.virtual_farms
    ADD CONSTRAINT virtual_farms_owner_id_key UNIQUE (owner_id);



ALTER TABLE ONLY public.virtual_farms
    ADD CONSTRAINT virtual_farms_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.world_entities
    ADD CONSTRAINT world_entities_pkey PRIMARY KEY (id);



CREATE INDEX economy_ledger_farm_idx ON public.economy_ledger USING btree (farm_id, created_at DESC);



CREATE INDEX farm_answers_user_idx ON public.farm_answers USING btree (user_id);



CREATE INDEX farm_outbox_pending_idx ON public.farm_outbox USING btree (created_at) WHERE (published_at IS NULL);



CREATE INDEX farm_outbox_pending_user_idx ON public.farm_outbox USING btree (user_id) WHERE (published_at IS NULL);



CREATE INDEX game_learning_outbox_pending_idx ON public.game_learning_outbox USING btree (next_attempt_at, created_at) WHERE (delivered_at IS NULL);



CREATE INDEX wild_insects_farm_expiry_idx ON public.farm_wild_insects USING btree (farm_id, expires_at);



CREATE UNIQUE INDEX world_entities_animal_slot_uq ON public.world_entities USING btree (farm_id, x, y) WHERE (category = 'ANIMAL'::text);



CREATE UNIQUE INDEX world_entities_non_animal_slot_uq ON public.world_entities USING btree (farm_id, x, y) WHERE (category <> 'ANIMAL'::text);



ALTER TABLE ONLY public.economy_ledger
    ADD CONSTRAINT economy_ledger_farm_id_fkey FOREIGN KEY (farm_id) REFERENCES public.virtual_farms(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.entity_runtime
    ADD CONSTRAINT entity_runtime_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.world_entities(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.farm_economy
    ADD CONSTRAINT farm_economy_farm_id_fkey FOREIGN KEY (farm_id) REFERENCES public.virtual_farms(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.farm_inventory
    ADD CONSTRAINT farm_inventory_farm_id_fkey FOREIGN KEY (farm_id) REFERENCES public.virtual_farms(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.farm_wild_insects
    ADD CONSTRAINT farm_wild_insects_farm_id_fkey FOREIGN KEY (farm_id) REFERENCES public.virtual_farms(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.game_harvest_receipts
    ADD CONSTRAINT game_harvest_receipts_challenge_id_fkey FOREIGN KEY (challenge_id) REFERENCES public.farm_answers(challenge_id);



ALTER TABLE ONLY public.game_learning_outbox
    ADD CONSTRAINT game_learning_outbox_challenge_id_fkey FOREIGN KEY (challenge_id) REFERENCES public.farm_answers(challenge_id);



ALTER TABLE ONLY public.world_entities
    ADD CONSTRAINT world_entities_farm_id_fkey FOREIGN KEY (farm_id) REFERENCES public.virtual_farms(id) ON DELETE CASCADE;

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
