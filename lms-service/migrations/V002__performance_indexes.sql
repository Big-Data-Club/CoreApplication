-- =============================================================================
-- V002__performance_indexes.sql
-- =============================================================================

-- ── users ────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ── user_roles ───────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role);

-- ── courses ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_courses_status     ON courses(status);
CREATE INDEX IF NOT EXISTS idx_courses_category   ON courses(category);
CREATE INDEX IF NOT EXISTS idx_courses_created_by ON courses(created_by);
CREATE INDEX IF NOT EXISTS idx_courses_level      ON courses(level);

-- ── course_sections ──────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sections_course ON course_sections(course_id);
CREATE INDEX IF NOT EXISTS idx_sections_order  ON course_sections(course_id, order_index);

-- ── section_content ──────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_content_section   ON section_content(section_id);
CREATE INDEX IF NOT EXISTS idx_content_type      ON section_content(type);
CREATE INDEX IF NOT EXISTS idx_content_order     ON section_content(section_id, order_index);
CREATE INDEX IF NOT EXISTS idx_content_ai_status ON section_content(ai_index_status)
    WHERE ai_index_status IN ('processing','indexed');
CREATE INDEX IF NOT EXISTS idx_section_content_section_mandatory
    ON section_content(section_id, id, is_mandatory)
    WHERE is_mandatory = true;

-- ── enrollments ──────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_enrollments_course         ON enrollments(course_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_student        ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_status         ON enrollments(status);
CREATE INDEX IF NOT EXISTS idx_enrollments_course_status  ON enrollments(course_id, status);
CREATE INDEX IF NOT EXISTS idx_enrollments_student_status ON enrollments(student_id, status);
CREATE INDEX IF NOT EXISTS idx_enrollments_course_accepted
    ON enrollments(course_id, student_id)
    WHERE status = 'ACCEPTED';

-- ── bulk_enrollment_logs ─────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_bulk_logs_course  ON bulk_enrollment_logs(course_id);
CREATE INDEX IF NOT EXISTS idx_bulk_logs_teacher ON bulk_enrollment_logs(teacher_id);
CREATE INDEX IF NOT EXISTS idx_bulk_logs_status  ON bulk_enrollment_logs(status);

-- ── quizzes ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_quizzes_content   ON quizzes(content_id);
CREATE INDEX IF NOT EXISTS idx_quizzes_published ON quizzes(is_published);
CREATE INDEX IF NOT EXISTS idx_quizzes_available ON quizzes(available_from, available_until);

-- ── quiz_questions ───────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_quiz_questions_quiz  ON quiz_questions(quiz_id);
CREATE INDEX IF NOT EXISTS idx_quiz_questions_order ON quiz_questions(quiz_id, order_index);
CREATE INDEX IF NOT EXISTS idx_quiz_questions_type  ON quiz_questions(question_type);
CREATE INDEX IF NOT EXISTS idx_quiz_questions_node  ON quiz_questions(node_id)
    WHERE node_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quiz_questions_bloom ON quiz_questions(bloom_level)
    WHERE bloom_level IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quiz_questions_settings ON quiz_questions USING gin(settings);
CREATE INDEX IF NOT EXISTS idx_quiz_questions_quiz_order
    ON quiz_questions(quiz_id, order_index)
    INCLUDE (points, question_type, node_id);

-- ── quiz_answer_options ───────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_answer_options_question ON quiz_answer_options(question_id);
CREATE INDEX IF NOT EXISTS idx_answer_options_blank    ON quiz_answer_options(question_id, blank_id);
CREATE INDEX IF NOT EXISTS idx_answer_options_blank_id ON quiz_answer_options(blank_id)
    WHERE blank_id IS NOT NULL;

-- ── quiz_correct_answers ──────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_correct_answers_question ON quiz_correct_answers(question_id);
CREATE INDEX IF NOT EXISTS idx_correct_answers_blank_id ON quiz_correct_answers(blank_id)
    WHERE blank_id IS NOT NULL;

-- ── quiz_attempts ─────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_quiz         ON quiz_attempts(quiz_id);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_student      ON quiz_attempts(student_id);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_status       ON quiz_attempts(status);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_quiz_student ON quiz_attempts(quiz_id, student_id);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_analytics
    ON quiz_attempts(quiz_id, student_id, status, percentage, is_passed)
    WHERE status IN ('SUBMITTED', 'GRADED');
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_student_status
    ON quiz_attempts(student_id, quiz_id, status, submitted_at)
    WHERE status IN ('SUBMITTED', 'GRADED');

-- ── quiz_student_answers ──────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_student_answers_attempt  ON quiz_student_answers(attempt_id);
CREATE INDEX IF NOT EXISTS idx_student_answers_question ON quiz_student_answers(question_id);
CREATE INDEX IF NOT EXISTS idx_student_answers_data     ON quiz_student_answers USING gin(answer_data);
CREATE INDEX IF NOT EXISTS idx_student_answers_attempt_grading
    ON quiz_student_answers(attempt_id, is_correct, points_earned)
    WHERE is_correct IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_student_answers_ungraded
    ON quiz_student_answers(attempt_id, question_id)
    WHERE points_earned IS NULL;

-- ── quiz_analytics ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_quiz_analytics_quiz     ON quiz_analytics(quiz_id);
CREATE INDEX IF NOT EXISTS idx_quiz_analytics_question ON quiz_analytics(question_id);

-- ── content_progress ─────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_content_progress_student         ON content_progress(student_id);
CREATE INDEX IF NOT EXISTS idx_content_progress_content         ON content_progress(content_id);
CREATE INDEX IF NOT EXISTS idx_content_progress_student_content ON content_progress(student_id, content_id);
CREATE INDEX IF NOT EXISTS idx_content_progress_content_student
    ON content_progress(content_id, student_id)
    INCLUDE (completed_at);
CREATE INDEX IF NOT EXISTS idx_content_progress_student_course
    ON content_progress(student_id, content_id);

-- ── forum_posts ───────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_forum_posts_content ON forum_posts(content_id);
CREATE INDEX IF NOT EXISTS idx_forum_posts_user    ON forum_posts(user_id);
CREATE INDEX IF NOT EXISTS idx_forum_posts_created ON forum_posts(content_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_forum_posts_pinned  ON forum_posts(content_id, is_pinned DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_forum_posts_tags    ON forum_posts USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_forum_posts_search  ON forum_posts
    USING GIN(to_tsvector('english', title || ' ' || body));
CREATE INDEX IF NOT EXISTS idx_forum_posts_score
    ON forum_posts(content_id, (upvotes - downvotes) DESC, created_at DESC)
    WHERE is_pinned = false;

-- ── forum_comments ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_forum_comments_post     ON forum_comments(post_id);
CREATE INDEX IF NOT EXISTS idx_forum_comments_parent   ON forum_comments(parent_comment_id);
CREATE INDEX IF NOT EXISTS idx_forum_comments_user     ON forum_comments(user_id);
CREATE INDEX IF NOT EXISTS idx_forum_comments_accepted ON forum_comments(post_id, is_accepted DESC);

-- ── forum_votes ───────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_forum_votes_votable ON forum_votes(votable_type, votable_id);
CREATE INDEX IF NOT EXISTS idx_forum_votes_user    ON forum_votes(user_id);

-- ── micro_lesson_jobs ─────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_micro_jobs_course  ON micro_lesson_jobs(course_id);
CREATE INDEX IF NOT EXISTS idx_micro_jobs_status  ON micro_lesson_jobs(status);
CREATE INDEX IF NOT EXISTS idx_micro_jobs_creator ON micro_lesson_jobs(created_by);

-- ── micro_lessons ─────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_micro_lessons_job        ON micro_lessons(job_id);
CREATE INDEX IF NOT EXISTS idx_micro_lessons_course     ON micro_lessons(course_id);
CREATE INDEX IF NOT EXISTS idx_micro_lessons_section    ON micro_lessons(section_id);
CREATE INDEX IF NOT EXISTS idx_micro_lessons_source     ON micro_lessons(source_content_id);
CREATE INDEX IF NOT EXISTS idx_micro_lessons_status     ON micro_lessons(status);
CREATE INDEX IF NOT EXISTS idx_micro_lessons_order      ON micro_lessons(job_id, order_index);
CREATE INDEX IF NOT EXISTS idx_micro_lessons_node_id    ON micro_lessons(node_id);

-- ── micro_lesson_interactions ─────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_mli_user_course   ON micro_lesson_interactions(user_id, course_id);
CREATE INDEX IF NOT EXISTS idx_mli_node          ON micro_lesson_interactions(node_id);
CREATE INDEX IF NOT EXISTS idx_mli_lesson        ON micro_lesson_interactions(lesson_id);
CREATE INDEX IF NOT EXISTS idx_mli_action        ON micro_lesson_interactions(action_type);
CREATE INDEX IF NOT EXISTS idx_mli_created_at    ON micro_lesson_interactions(created_at DESC);

-- ── knowledge_node_mastery ────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_knm_course_node ON knowledge_node_mastery(course_id, node_id);
CREATE INDEX IF NOT EXISTS idx_knm_user_course ON knowledge_node_mastery(user_id, course_id);

-- ── Analyze updated tables so planner picks up new indexes immediately ────────
ANALYZE users;
ANALYZE user_roles;
ANALYZE courses;
ANALYZE course_sections;
ANALYZE section_content;
ANALYZE enrollments;
ANALYZE bulk_enrollment_logs;
ANALYZE quizzes;
ANALYZE quiz_questions;
ANALYZE quiz_answer_options;
ANALYZE quiz_correct_answers;
ANALYZE quiz_attempts;
ANALYZE quiz_student_answers;
ANALYZE quiz_analytics;
ANALYZE content_progress;
ANALYZE forum_posts;
ANALYZE forum_comments;
ANALYZE forum_votes;
ANALYZE micro_lesson_jobs;
ANALYZE micro_lessons;
ANALYZE micro_lesson_interactions;
ANALYZE knowledge_node_mastery;
