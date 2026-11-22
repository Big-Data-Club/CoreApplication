-- Dashboard queries stay constrained to the teacher's courses and first
-- completed attempt per student/quiz. These partial indexes keep cold-cache
-- dashboard loads fast as course and quiz data grow.
CREATE INDEX IF NOT EXISTS idx_courses_teacher_published
    ON courses(created_by, id)
    WHERE status = 'PUBLISHED';

CREATE INDEX IF NOT EXISTS idx_enrollments_accepted_timeline
    ON enrollments(course_id, enrolled_at DESC, student_id)
    WHERE status = 'ACCEPTED';

CREATE INDEX IF NOT EXISTS idx_quiz_attempts_dashboard_first
    ON quiz_attempts(quiz_id, student_id, attempt_number, id)
    INCLUDE (percentage)
    WHERE status IN ('SUBMITTED', 'GRADED');
