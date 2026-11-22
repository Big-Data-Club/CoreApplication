CREATE TABLE IF NOT EXISTS virtual_farms (
 id UUID PRIMARY KEY, owner_id BIGINT UNIQUE NOT NULL CHECK(owner_id>0),
 name VARCHAR(100) NOT NULL, coins INT NOT NULL DEFAULT 900 CHECK(coins>=0),
 xp INT NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS world_entities (
 id UUID PRIMARY KEY, farm_id UUID NOT NULL REFERENCES virtual_farms(id) ON DELETE CASCADE,
 category TEXT NOT NULL CHECK(category IN ('CROP','ANIMAL','STRUCTURE','DECOR')),
 kind TEXT NOT NULL, x INT NOT NULL CHECK(x BETWEEN 0 AND 19), y INT NOT NULL CHECK(y BETWEEN 0 AND 13),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE UNIQUE INDEX IF NOT EXISTS world_entities_non_animal_slot_uq ON world_entities(farm_id,x,y) WHERE category<>'ANIMAL';
CREATE UNIQUE INDEX IF NOT EXISTS world_entities_animal_slot_uq ON world_entities(farm_id,x,y) WHERE category='ANIMAL';
CREATE TABLE IF NOT EXISTS farm_economy (
  farm_id UUID PRIMARY KEY REFERENCES virtual_farms(id) ON DELETE CASCADE,
  last_tick TIMESTAMPTZ NOT NULL DEFAULT now(),
  hunger_seconds INT NOT NULL DEFAULT 1800 CHECK(hunger_seconds>=0),
  insects INT NOT NULL DEFAULT 1 CHECK(insects BETWEEN 0 AND 4),
  insect_last_spawn TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_catch TIMESTAMPTZ NOT NULL DEFAULT '2000-01-01',
  tutorial_step INT NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS farm_inventory (
  farm_id UUID NOT NULL REFERENCES virtual_farms(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  quantity INT NOT NULL DEFAULT 0 CHECK(quantity>=0),
  PRIMARY KEY(farm_id,kind)
);
CREATE TABLE IF NOT EXISTS entity_runtime (
  entity_id UUID PRIMARY KEY REFERENCES world_entities(id) ON DELETE CASCADE,
  last_tick TIMESTAMPTZ NOT NULL DEFAULT now(),
  work_seconds INT NOT NULL DEFAULT 0,
  work_remainder INT NOT NULL DEFAULT 0,
  hunger_seconds INT NOT NULL DEFAULT 480,
  starvation_seconds INT NOT NULL DEFAULT 0,
  water_seconds INT NOT NULL DEFAULT 0,
  health INT NOT NULL DEFAULT 100 CHECK(health BETWEEN 0 AND 100),
  sick BOOLEAN NOT NULL DEFAULT FALSE,
  yield_ready INT NOT NULL DEFAULT 0,
  oxygen INT NOT NULL DEFAULT 100 CHECK(oxygen BETWEEN 0 AND 100),
  oxygen_age_seconds INT NOT NULL DEFAULT 0,
  build_until TIMESTAMPTZ,
  last_petted TIMESTAMPTZ NOT NULL DEFAULT '2000-01-01'
);
CREATE TABLE IF NOT EXISTS economy_ledger (
  id UUID PRIMARY KEY,
  farm_id UUID NOT NULL REFERENCES virtual_farms(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  kind TEXT NOT NULL,
  quantity INT NOT NULL DEFAULT 0,
  coins_delta INT NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS economy_ledger_farm_idx ON economy_ledger(farm_id,created_at DESC);


-- Persistent insect entities. Existing player farms are preserved.
ALTER TABLE farm_economy ADD COLUMN IF NOT EXISTS insect_seeded BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS farm_wild_insects (
  id UUID PRIMARY KEY,
  farm_id UUID NOT NULL REFERENCES virtual_farms(id) ON DELETE CASCADE,
  species TEXT NOT NULL CHECK (species IN ('ladybug','grasshopper','butterfly','dragonfly')),
  x SMALLINT NOT NULL CHECK (x BETWEEN 0 AND 19),
  y SMALLINT NOT NULL CHECK (y BETWEEN 0 AND 13),
  spawned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  UNIQUE (farm_id,x,y)
);
CREATE INDEX IF NOT EXISTS wild_insects_farm_expiry_idx ON farm_wild_insects(farm_id,expires_at);


-- Harvested crops remain on their original plots; cooldown and rewatering
-- state survive browser reloads and backend restarts.
ALTER TABLE entity_runtime
  ADD COLUMN IF NOT EXISTS regrow_until TIMESTAMPTZ;


CREATE TABLE IF NOT EXISTS game_learning (
 user_id BIGINT NOT NULL, entity_id UUID NOT NULL, action TEXT NOT NULL,
 state JSONB NOT NULL, PRIMARY KEY(user_id,entity_id,action));
CREATE TABLE IF NOT EXISTS game_harvest_receipts (
 challenge_id UUID PRIMARY KEY REFERENCES farm_answers(challenge_id),
 user_id BIGINT NOT NULL, entity_id UUID NOT NULL, action TEXT NOT NULL);
