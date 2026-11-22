-- Applied idempotently by LakehouseService._init_tables under its DuckDB lock.
-- Existing notes retain NULL annotations; update/delete remains owner-scoped.
ALTER TABLE notebook_entries ADD COLUMN IF NOT EXISTS annotation TEXT;
