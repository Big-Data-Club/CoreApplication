-- V003__dynamic_roles.sql
-- Enable fully dynamic roles in LMS: drop hardcoded CHECK constraint,
-- add source tracking for sync vs manual role assignments, and create
-- a role_definitions table for admin CRUD.

-- 1. Drop hardcoded role CHECK constraint
ALTER TABLE user_roles DROP CONSTRAINT IF EXISTS user_roles_role_check;

-- 2. Add source column to distinguish synced vs manually assigned roles
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_roles' AND column_name = 'source'
    ) THEN
        ALTER TABLE user_roles ADD COLUMN source VARCHAR(10) DEFAULT 'sync'
            CHECK (source IN ('sync', 'manual'));
    END IF;
END $$;

-- 3. LMS-side role definitions (admin can CRUD these)
CREATE TABLE IF NOT EXISTS role_definitions (
    id           BIGSERIAL PRIMARY KEY,
    name         VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100),
    description  TEXT,
    is_system    BOOLEAN DEFAULT false,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Seed existing well-known roles
INSERT INTO role_definitions (name, display_name, is_system) VALUES
    ('STUDENT', 'Student', true),
    ('TEACHER', 'Teacher', true),
    ('ADMIN',   'Administrator', true)
ON CONFLICT (name) DO NOTHING;

-- 5. Update existing user_roles rows to have source='sync'
UPDATE user_roles SET source = 'sync' WHERE source IS NULL;
