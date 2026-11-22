ALTER TABLE courses
    ADD COLUMN IF NOT EXISTS archived_from_status VARCHAR(50);

ALTER TABLE courses
    DROP CONSTRAINT IF EXISTS courses_archived_from_status_check;

ALTER TABLE courses
    ADD CONSTRAINT courses_archived_from_status_check
    CHECK (archived_from_status IS NULL OR archived_from_status IN ('DRAFT', 'PUBLISHED'));
