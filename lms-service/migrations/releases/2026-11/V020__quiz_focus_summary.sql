-- Bounded browser-reported aggregate; no per-event writes or additional indexes.
ALTER TABLE quiz_attempts ADD COLUMN focus_summary JSONB;
