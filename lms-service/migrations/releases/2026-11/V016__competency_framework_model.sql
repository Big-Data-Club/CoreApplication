-- V016: Universal competency framework model
--
-- Personalization must be independent of a subject area. A competency belongs
-- to a versioned framework owned by an organization (or to a global framework
-- when organization_id is NULL). Course authors then align courses, content,
-- and questions to those competencies. No programming, maths, or other
-- domain-specific data is seeded by a database migration.

CREATE TABLE IF NOT EXISTS competency_frameworks (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    code VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    subject VARCHAR(100),
    locale VARCHAR(20) NOT NULL DEFAULT 'und',
    version VARCHAR(50) NOT NULL DEFAULT '1.0',
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- PostgreSQL treats NULL values as distinct in a normal unique constraint, so
-- separate indexes express the intended global and organization-scoped rules.
CREATE UNIQUE INDEX IF NOT EXISTS uq_competency_frameworks_global_code
    ON competency_frameworks(code) WHERE organization_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_competency_frameworks_org_code
    ON competency_frameworks(organization_id, code) WHERE organization_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_competency_frameworks_organization
    ON competency_frameworks(organization_id, status);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_competency_frameworks_updated_at'
                   AND tgrelid = 'competency_frameworks'::regclass) THEN
        CREATE TRIGGER update_competency_frameworks_updated_at
            BEFORE UPDATE ON competency_frameworks
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- Extend the V015 skills table into a reusable competency catalogue. Existing
-- rows remain valid: framework_id and code are nullable for legacy data until
-- it is assigned to a framework through the admin/import workflow.
ALTER TABLE skills
    ADD COLUMN IF NOT EXISTS framework_id BIGINT REFERENCES competency_frameworks(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS code VARCHAR(100),
    ADD COLUMN IF NOT EXISTS competency_type VARCHAR(30) NOT NULL DEFAULT 'KNOWLEDGE'
        CHECK (competency_type IN ('KNOWLEDGE', 'SKILL', 'ATTITUDE', 'OUTCOME')),
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

-- `UNIQUE(name)` from V015 prevents two frameworks from using natural names
-- such as "Problem solving". Identity is now framework + stable code.
ALTER TABLE skills DROP CONSTRAINT IF EXISTS skills_name_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_skills_framework_code
    ON skills(framework_id, code)
    WHERE framework_id IS NOT NULL AND code IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_skills_global_code
    ON skills(code)
    WHERE framework_id IS NULL AND code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_skills_framework
    ON skills(framework_id, status);

-- A course can declare its intended outcomes independently of which individual
-- lesson or assessment provides evidence for them.
CREATE TABLE IF NOT EXISTS course_competencies (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    skill_id BIGINT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    target_mastery FLOAT NOT NULL DEFAULT 0.8 CHECK (target_mastery >= 0 AND target_mastery <= 1),
    weight FLOAT NOT NULL DEFAULT 1.0 CHECK (weight >= 0 AND weight <= 1),
    is_required BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(course_id, skill_id)
);
CREATE INDEX IF NOT EXISTS idx_course_competencies_course ON course_competencies(course_id);
CREATE INDEX IF NOT EXISTS idx_course_competencies_skill ON course_competencies(skill_id);

-- Generic, typed relations support prerequisite graphs as well as hierarchy,
-- cross-framework equivalence, and related-topic discovery. The old
-- skill_prerequisites table remains for backwards compatibility with V015 APIs.
CREATE TABLE IF NOT EXISTS skill_relationships (
    id BIGSERIAL PRIMARY KEY,
    source_skill_id BIGINT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    target_skill_id BIGINT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    relationship_type VARCHAR(30) NOT NULL
        CHECK (relationship_type IN ('PREREQUISITE', 'PART_OF', 'RELATED', 'EQUIVALENT')),
    strength FLOAT NOT NULL DEFAULT 1.0 CHECK (strength >= 0 AND strength <= 1),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_skill_id, target_skill_id, relationship_type),
    CHECK (source_skill_id <> target_skill_id)
);
CREATE INDEX IF NOT EXISTS idx_skill_relationships_source ON skill_relationships(source_skill_id, relationship_type);
CREATE INDEX IF NOT EXISTS idx_skill_relationships_target ON skill_relationships(target_skill_id, relationship_type);

-- Preserve existing prerequisite records in the generalized graph. This is
-- idempotent and becomes a no-op for a new installation with no seed data.
INSERT INTO skill_relationships (source_skill_id, target_skill_id, relationship_type, strength)
SELECT skill_id, prerequisite_skill_id, 'PREREQUISITE', strength
FROM skill_prerequisites
ON CONFLICT (source_skill_id, target_skill_id, relationship_type) DO NOTHING;

-- Content and question mappings from V015 are deliberately retained: they are
-- the evidence links used to update learner competency state. Framework and
-- course alignment are enforced by the authoring/API layer, not hard-coded SQL.
