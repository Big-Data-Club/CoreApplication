CREATE TABLE IF NOT EXISTS enrollments (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    student_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'WAITING',
    enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    accepted_at TIMESTAMP,
    rejected_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(course_id, student_id)
);

CREATE INDEX idx_enrollments_course ON enrollments(course_id);
CREATE INDEX idx_enrollments_student ON enrollments(student_id);
CREATE INDEX idx_enrollments_status ON enrollments(status);
CREATE INDEX idx_enrollments_course_status ON enrollments(course_id, status);
CREATE INDEX idx_enrollments_student_status ON enrollments(student_id, status);

-- ============================================
-- BULK ENROLLMENT LOGS (For tracking bulk operations)
-- ============================================

CREATE TABLE IF NOT EXISTS bulk_enrollment_logs (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    teacher_id BIGINT NOT NULL,
    total_count INT NOT NULL,
    success_count INT DEFAULT 0,
    failed_count INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'PROCESSING', -- PROCESSING, COMPLETED, FAILED
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_bulk_logs_course ON bulk_enrollment_logs(course_id);
CREATE INDEX idx_bulk_logs_teacher ON bulk_enrollment_logs(teacher_id);
CREATE INDEX idx_bulk_logs_status ON bulk_enrollment_logs(status);

-- ============================================
-- UPDATE TRIGGERS
-- ============================================

CREATE TRIGGER update_enrollments_updated_at
BEFORE UPDATE ON enrollments
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_bulk_enrollment_logs_updated_at
BEFORE UPDATE ON bulk_enrollment_logs
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
