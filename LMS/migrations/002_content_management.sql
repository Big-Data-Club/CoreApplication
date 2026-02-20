-- LMS Database Schema
-- Users and Courses with Role Management

-- ============================================
-- USERS TABLE (Basic user info from auth service)
-- ============================================

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);

-- ============================================
-- USER ROLES (Many-to-many relationship)
-- ============================================

CREATE TABLE IF NOT EXISTS user_roles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL CHECK (role IN ('STUDENT', 'TEACHER', 'ADMIN')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, role)
);

CREATE INDEX idx_user_roles_user ON user_roles(user_id);
CREATE INDEX idx_user_roles_role ON user_roles(role);

-- ============================================
-- COURSES TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS courses (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    level VARCHAR(50) CHECK (level IN ('BEGINNER', 'INTERMEDIATE', 'ADVANCED', 'ALL_LEVELS')),
    thumbnail_url VARCHAR(500),
    status VARCHAR(50) DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')),
    created_by BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP
);

CREATE INDEX idx_courses_status ON courses(status);
CREATE INDEX idx_courses_category ON courses(category);
CREATE INDEX idx_courses_created_by ON courses(created_by);
CREATE INDEX idx_courses_level ON courses(level);

-- ============================================
-- COURSE SECTIONS
-- ============================================

CREATE TABLE IF NOT EXISTS course_sections (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    order_index INTEGER NOT NULL,
    is_published BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sections_course ON course_sections(course_id);
CREATE INDEX idx_sections_order ON course_sections(course_id, order_index);

-- ============================================
-- SECTION CONTENT
-- ============================================

CREATE TABLE IF NOT EXISTS section_content (
    id BIGSERIAL PRIMARY KEY,
    section_id BIGINT NOT NULL REFERENCES course_sections(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL CHECK (type IN ('TEXT', 'VIDEO', 'DOCUMENT', 'IMAGE', 'QUIZ', 'FORUM', 'ANNOUNCEMENT')),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    order_index INTEGER NOT NULL,
    metadata JSONB,
    is_published BOOLEAN DEFAULT false,
    is_mandatory BOOLEAN DEFAULT false,
    file_path VARCHAR(1000),
    file_size BIGINT,
    file_type VARCHAR(100),
    created_by BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_content_section ON section_content(section_id);
CREATE INDEX idx_content_type ON section_content(type);
CREATE INDEX idx_content_order ON section_content(section_id, order_index);

-- ============================================
-- UPDATE TRIGGERS
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_courses_updated_at
    BEFORE UPDATE ON courses
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_course_sections_updated_at
    BEFORE UPDATE ON course_sections
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_section_content_updated_at
    BEFORE UPDATE ON section_content
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();