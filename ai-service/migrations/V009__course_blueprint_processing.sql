-- Long-running blueprint generation must survive the browser/proxy request
-- boundary.  PROCESSING/FAILED are persisted states, not transient HTTP
-- errors, so the client can poll and the teacher can retry safely.
ALTER TABLE course_blueprints
    DROP CONSTRAINT IF EXISTS course_blueprints_status_check;

ALTER TABLE course_blueprints
    ADD CONSTRAINT course_blueprints_status_check
    CHECK (status IN ('PROCESSING', 'DRAFT', 'APPROVED', 'CANCELLED', 'APPLIED', 'FAILED'));

ALTER TABLE course_blueprints
    ADD COLUMN IF NOT EXISTS error_message TEXT;
