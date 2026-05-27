-- V005__organizations.sql
-- Create organizations, organization_members tables, and add org relationship to courses

CREATE TABLE IF NOT EXISTS organizations (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    slug        VARCHAR(100) NOT NULL UNIQUE,   -- URL-safe identifier
    description TEXT,
    logo_url    VARCHAR(500),
    is_active   BOOLEAN NOT NULL DEFAULT true,
    settings    JSONB   NOT NULL DEFAULT '{
        "allow_cross_org_courses": true,
        "default_course_visibility": "PUBLIC"
    }'::jsonb,
    created_by  BIGINT REFERENCES users(id),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- many-to-many: users ↔ organizations
CREATE TABLE IF NOT EXISTS organization_members (
    id        BIGSERIAL PRIMARY KEY,
    org_id    BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id   BIGINT NOT NULL REFERENCES users(id)         ON DELETE CASCADE,
    org_role  VARCHAR(20) NOT NULL DEFAULT 'MEMBER'
              CHECK (org_role IN ('OWNER','ADMIN','MEMBER')),
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(org_id, user_id)
);

-- Add org ownership + visibility to courses
ALTER TABLE courses
    ADD COLUMN IF NOT EXISTS org_id     BIGINT REFERENCES organizations(id),
    ADD COLUMN IF NOT EXISTS visibility VARCHAR(20) DEFAULT 'PUBLIC'
        CHECK (visibility IN ('PUBLIC','ORG_ONLY'));

-- Seed default org
INSERT INTO organizations (name, slug, description, is_active)
    VALUES ('Big Data Club', 'bdc', 'Default organization', true)
    ON CONFLICT (slug) DO NOTHING;

-- Migrate existing courses → default org, all PUBLIC
UPDATE courses
SET org_id = (SELECT id FROM organizations WHERE slug = 'bdc'),
    visibility = 'PUBLIC'
WHERE org_id IS NULL;

-- Migrate existing users → default org as MEMBER
INSERT INTO organization_members (org_id, user_id, org_role)
SELECT (SELECT id FROM organizations WHERE slug = 'bdc'), id, 'MEMBER'
FROM   users
ON CONFLICT (org_id, user_id) DO NOTHING;

-- Make org_id NOT NULL after backfill
ALTER TABLE courses ALTER COLUMN org_id SET NOT NULL;
