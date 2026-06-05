-- Add detailed agent logs to section overview jobs
ALTER TABLE section_overview_jobs ADD COLUMN logs TEXT NOT NULL DEFAULT '';
