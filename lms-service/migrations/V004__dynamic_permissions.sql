-- V004__dynamic_permissions.sql
-- Granular, dynamic permission system for LMS roles.
-- Replaces hardcoded role checks with configurable permission assignments.

-- 1. Master permission table
CREATE TABLE IF NOT EXISTS permissions (
    id          BIGSERIAL PRIMARY KEY,
    code        VARCHAR(80) UNIQUE NOT NULL,
    module      VARCHAR(40) NOT NULL,
    description VARCHAR(255),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. N-N junction: which role holds which permissions
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       BIGINT NOT NULL REFERENCES role_definitions(id) ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    assigned_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (role_id, permission_id)
);

CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions(role_id);

-- 3. Seed permissions
INSERT INTO permissions (code, module, description) VALUES
    -- Course management
    ('COURSE_VIEW',      'COURSE',     'View course details and content'),
    ('COURSE_CREATE',    'COURSE',     'Create new courses'),
    ('COURSE_EDIT',      'COURSE',     'Edit existing courses'),
    ('COURSE_DELETE',    'COURSE',     'Delete courses'),
    ('COURSE_PUBLISH',   'COURSE',     'Publish or unpublish courses'),
    -- Quiz management
    ('QUIZ_CREATE',      'QUIZ',       'Create quizzes and questions'),
    ('QUIZ_EDIT',        'QUIZ',       'Edit existing quizzes'),
    ('QUIZ_DELETE',      'QUIZ',       'Delete quizzes'),
    ('QUIZ_GRADE',       'QUIZ',       'Grade quiz attempts'),
    -- Enrollment management
    ('ENROLLMENT_MANAGE','ENROLLMENT', 'Approve or reject enrollments'),
    ('ENROLLMENT_BULK',  'ENROLLMENT', 'Bulk enroll students'),
    -- AI features
    ('AI_INDEX',         'AI',         'Trigger document AI indexing'),
    ('AI_GENERATE',      'AI',         'Generate AI content (lessons, quizzes)'),
    -- System administration
    ('ROLE_MANAGE',      'SYSTEM',     'Manage roles and permissions'),
    ('ANALYTICS_VIEW',   'SYSTEM',     'View analytics and reports')
ON CONFLICT (code) DO NOTHING;

-- 4. Auto-assign ALL permissions to ADMIN role
INSERT INTO role_permissions (role_id, permission_id)
SELECT rd.id, p.id
FROM role_definitions rd
CROSS JOIN permissions p
WHERE rd.name = 'ADMIN'
ON CONFLICT DO NOTHING;

-- 5. Auto-assign teacher-relevant permissions to TEACHER role
INSERT INTO role_permissions (role_id, permission_id)
SELECT rd.id, p.id
FROM role_definitions rd
CROSS JOIN permissions p
WHERE rd.name = 'TEACHER'
  AND p.code IN (
    'COURSE_VIEW', 'COURSE_CREATE', 'COURSE_EDIT', 'COURSE_PUBLISH',
    'QUIZ_CREATE', 'QUIZ_EDIT', 'QUIZ_GRADE',
    'ENROLLMENT_MANAGE', 'ENROLLMENT_BULK',
    'AI_INDEX', 'AI_GENERATE',
    'ANALYTICS_VIEW'
  )
ON CONFLICT DO NOTHING;

-- 6. Auto-assign student permissions to STUDENT role
INSERT INTO role_permissions (role_id, permission_id)
SELECT rd.id, p.id
FROM role_definitions rd
CROSS JOIN permissions p
WHERE rd.name = 'STUDENT'
  AND p.code IN ('COURSE_VIEW')
ON CONFLICT DO NOTHING;
