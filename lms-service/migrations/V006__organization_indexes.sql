-- V006__organization_indexes.sql
-- Performance indexes for organization queries

-- Primary access pattern: "courses visible to user X"
CREATE INDEX IF NOT EXISTS idx_courses_org_visibility_status
    ON courses (org_id, visibility, status);

-- Membership lookups (most frequent path)
CREATE INDEX IF NOT EXISTS idx_org_members_user_id   ON organization_members (user_id);
CREATE INDEX IF NOT EXISTS idx_org_members_org_id    ON organization_members (org_id);

-- Org listing
CREATE INDEX IF NOT EXISTS idx_organizations_is_active ON organizations (is_active);

-- Covering index for course-list query hot path
CREATE INDEX IF NOT EXISTS idx_courses_org_status_pub  ON courses (org_id, status, published_at DESC)
    WHERE status = 'PUBLISHED';
