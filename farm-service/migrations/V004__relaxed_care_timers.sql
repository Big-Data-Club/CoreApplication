-- Applied by the embedded game schema at service startup. Kept separately as
-- the forward-only migration record for external database rollout tooling.
ALTER TABLE farm_economy ADD COLUMN IF NOT EXISTS care_rules_version INT NOT NULL DEFAULT 1;
ALTER TABLE farm_economy ALTER COLUMN hunger_seconds SET DEFAULT 43200;
ALTER TABLE entity_runtime ALTER COLUMN hunger_seconds SET DEFAULT 43200;
