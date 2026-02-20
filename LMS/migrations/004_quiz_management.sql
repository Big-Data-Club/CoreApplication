-- ============================================
-- QUIZ SYSTEM
-- ============================================

-- Quiz Configuration Table
CREATE TABLE IF NOT EXISTS quizzes (
    id BIGSERIAL PRIMARY KEY,
    content_id BIGINT NOT NULL REFERENCES section_content(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    instructions TEXT,
    
    -- Timing settings
    time_limit_minutes INTEGER, -- NULL = unlimited
    available_from TIMESTAMP,
    available_until TIMESTAMP,
    
    -- Attempt settings
    max_attempts INTEGER DEFAULT 1, -- NULL = unlimited
    shuffle_questions BOOLEAN DEFAULT false,
    shuffle_answers BOOLEAN DEFAULT false,
    
    -- Grading settings
    passing_score DECIMAL(5,2), -- percentage or points
    total_points DECIMAL(10,2) DEFAULT 100.00,
    auto_grade BOOLEAN DEFAULT true, -- auto grade objective questions
    
    -- Display settings
    show_results_immediately BOOLEAN DEFAULT true, -- show score after submission
    show_correct_answers BOOLEAN DEFAULT true, -- show correct answers after submission
    allow_review BOOLEAN DEFAULT true, -- allow students to review their submission
    show_feedback BOOLEAN DEFAULT true, -- show question feedback
    
    -- Status
    is_published BOOLEAN DEFAULT false,
    
    created_by BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quizzes_content ON quizzes(content_id);
CREATE INDEX idx_quizzes_published ON quizzes(is_published);
CREATE INDEX idx_quizzes_available ON quizzes(available_from, available_until);

-- Question Types:
-- - SINGLE_CHOICE: Multiple choice with single correct answer
-- - MULTIPLE_CHOICE: Multiple choice with multiple correct answers
-- - SHORT_ANSWER: Short text answer (word limit)
-- - ESSAY: Long text answer (no limit)
-- - FILE_UPLOAD: Upload file as answer
-- - FILL_BLANK_TEXT: Fill in the blank (manual input)
-- - FILL_BLANK_DROPDOWN: Fill in the blank (dropdown options)

CREATE TABLE IF NOT EXISTS quiz_questions (
    id BIGSERIAL PRIMARY KEY,
    quiz_id BIGINT NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    question_type VARCHAR(50) NOT NULL CHECK (question_type IN (
        'SINGLE_CHOICE', 'MULTIPLE_CHOICE', 'SHORT_ANSWER', 'ESSAY', 
        'FILE_UPLOAD', 'FILL_BLANK_TEXT', 'FILL_BLANK_DROPDOWN'
    )),
    
    question_text TEXT NOT NULL,
    question_html TEXT, -- Rich text version
    explanation TEXT, -- Feedback/explanation shown after submission
    
    points DECIMAL(10,2) DEFAULT 10.00,
    order_index INTEGER NOT NULL,
    
    -- Type-specific settings stored as JSONB for flexibility
    settings JSONB DEFAULT '{}',
    -- Examples:
    -- SHORT_ANSWER: {"max_words": 100, "case_sensitive": false}
    -- FILE_UPLOAD: {"allowed_types": ["pdf", "docx"], "max_size_mb": 10}
    -- FILL_BLANK: {"blanks": [{"id": 1, "position": 15}]}
    
    is_required BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quiz_questions_quiz ON quiz_questions(quiz_id);
CREATE INDEX idx_quiz_questions_order ON quiz_questions(quiz_id, order_index);
CREATE INDEX idx_quiz_questions_type ON quiz_questions(question_type);

-- Answer Options (for choice questions)
CREATE TABLE IF NOT EXISTS quiz_answer_options (
    id BIGSERIAL PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES quiz_questions(id) ON DELETE CASCADE,
    option_text TEXT NOT NULL,
    option_html TEXT, -- Rich text version
    is_correct BOOLEAN DEFAULT false,
    order_index INTEGER NOT NULL,
    
    -- For fill-in-the-blank dropdown
    blank_id INTEGER, -- which blank this option belongs to
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_answer_options_question ON quiz_answer_options(question_id);
CREATE INDEX idx_answer_options_blank ON quiz_answer_options(question_id, blank_id);

-- Correct Answers (for non-choice questions)
CREATE TABLE IF NOT EXISTS quiz_correct_answers (
    id BIGSERIAL PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES quiz_questions(id) ON DELETE CASCADE,
    
    -- For text-based answers
    answer_text TEXT,
    
    -- For fill-in-the-blank
    blank_id INTEGER,
    blank_position INTEGER, -- position in text where blank appears
    
    -- Matching options
    case_sensitive BOOLEAN DEFAULT false,
    exact_match BOOLEAN DEFAULT false, -- or allow partial match
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_correct_answers_question ON quiz_correct_answers(question_id);

-- Student Quiz Attempts
CREATE TABLE IF NOT EXISTS quiz_attempts (
    id BIGSERIAL PRIMARY KEY,
    quiz_id BIGINT NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    student_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    attempt_number INTEGER NOT NULL DEFAULT 1,
    
    -- Timing
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMP,
    time_spent_seconds INTEGER, -- actual time spent
    
    -- Scoring
    total_points DECIMAL(10,2),
    earned_points DECIMAL(10,2),
    percentage DECIMAL(5,2),
    is_passed BOOLEAN,
    
    -- Status
    status VARCHAR(20) DEFAULT 'IN_PROGRESS' CHECK (status IN (
        'IN_PROGRESS', 'SUBMITTED', 'GRADED', 'ABANDONED'
    )),
    
    -- Grading
    auto_graded_at TIMESTAMP,
    manually_graded_at TIMESTAMP,
    graded_by BIGINT REFERENCES users(id),
    
    -- Metadata
    ip_address VARCHAR(45),
    user_agent TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(quiz_id, student_id, attempt_number)
);

CREATE INDEX idx_quiz_attempts_quiz ON quiz_attempts(quiz_id);
CREATE INDEX idx_quiz_attempts_student ON quiz_attempts(student_id);
CREATE INDEX idx_quiz_attempts_status ON quiz_attempts(status);
CREATE INDEX idx_quiz_attempts_quiz_student ON quiz_attempts(quiz_id, student_id);

-- Student Answers
CREATE TABLE IF NOT EXISTS quiz_student_answers (
    id BIGSERIAL PRIMARY KEY,
    attempt_id BIGINT NOT NULL REFERENCES quiz_attempts(id) ON DELETE CASCADE,
    question_id BIGINT NOT NULL REFERENCES quiz_questions(id) ON DELETE CASCADE,
    
    -- Answer data (JSONB for flexibility across question types)
    answer_data JSONB NOT NULL,
    -- Examples:
    -- SINGLE_CHOICE: {"selected_option_id": 123}
    -- MULTIPLE_CHOICE: {"selected_option_ids": [123, 456]}
    -- SHORT_ANSWER/ESSAY: {"text": "student answer here"}
    -- FILE_UPLOAD: {"file_path": "...", "file_name": "...", "file_size": 1024}
    -- FILL_BLANK_TEXT: {"blanks": [{"blank_id": 1, "answer": "text"}]}
    -- FILL_BLANK_DROPDOWN: {"blanks": [{"blank_id": 1, "selected_option_id": 789}]}
    
    -- Scoring
    points_earned DECIMAL(10,2),
    is_correct BOOLEAN, -- for auto-gradable questions
    
    -- Manual grading
    grader_feedback TEXT,
    graded_by BIGINT REFERENCES users(id),
    graded_at TIMESTAMP,
    
    -- Metadata
    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    time_spent_seconds INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(attempt_id, question_id)
);

CREATE INDEX idx_student_answers_attempt ON quiz_student_answers(attempt_id);
CREATE INDEX idx_student_answers_question ON quiz_student_answers(question_id);
CREATE INDEX idx_student_answers_grading ON quiz_student_answers(graded_by) WHERE graded_by IS NOT NULL;

-- Quiz Analytics (for teacher insights)
CREATE TABLE IF NOT EXISTS quiz_analytics (
    id BIGSERIAL PRIMARY KEY,
    quiz_id BIGINT NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    question_id BIGINT REFERENCES quiz_questions(id) ON DELETE CASCADE,
    
    -- Question-level analytics
    total_attempts INTEGER DEFAULT 0,
    correct_count INTEGER DEFAULT 0,
    incorrect_count INTEGER DEFAULT 0,
    average_score DECIMAL(5,2),
    
    -- Difficulty indicator (calculated)
    difficulty_rating VARCHAR(20), -- EASY, MEDIUM, HARD
    
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(quiz_id, question_id)
);

CREATE INDEX idx_quiz_analytics_quiz ON quiz_analytics(quiz_id);
CREATE INDEX idx_quiz_analytics_question ON quiz_analytics(question_id);

-- ============================================
-- TRIGGERS
-- ============================================

CREATE TRIGGER update_quizzes_updated_at
BEFORE UPDATE ON quizzes
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_quiz_questions_updated_at
BEFORE UPDATE ON quiz_questions
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_quiz_attempts_updated_at
BEFORE UPDATE ON quiz_attempts
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_quiz_student_answers_updated_at
BEFORE UPDATE ON quiz_student_answers
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Function to auto-grade objective questions
CREATE OR REPLACE FUNCTION auto_grade_quiz_answer(
    p_answer_id BIGINT
) RETURNS BOOLEAN AS $$
DECLARE
    v_question_type VARCHAR(50);
    v_answer_data JSONB;
    v_is_correct BOOLEAN;
    v_points DECIMAL(10,2);
BEGIN
    -- Get question type and answer data
    SELECT qq.question_type, qq.points, qsa.answer_data
    INTO v_question_type, v_points, v_answer_data
    FROM quiz_student_answers qsa
    JOIN quiz_questions qq ON qsa.question_id = qq.id
    WHERE qsa.id = p_answer_id;
    
    -- Auto-grade based on question type
    IF v_question_type = 'SINGLE_CHOICE' THEN
        -- Check if selected option is correct
        SELECT qao.is_correct INTO v_is_correct
        FROM quiz_answer_options qao
        WHERE qao.id = (v_answer_data->>'selected_option_id')::BIGINT;
        
    ELSIF v_question_type = 'MULTIPLE_CHOICE' THEN
        -- Check if all and only correct options are selected
        WITH selected AS (
            SELECT jsonb_array_elements_text(v_answer_data->'selected_option_ids')::BIGINT AS option_id
        ),
        correct_options AS (
            SELECT id FROM quiz_answer_options 
            WHERE question_id = (SELECT question_id FROM quiz_student_answers WHERE id = p_answer_id)
            AND is_correct = true
        )
        SELECT 
            (SELECT COUNT(*) FROM selected WHERE option_id IN (SELECT id FROM correct_options)) = 
            (SELECT COUNT(*) FROM correct_options) AND
            (SELECT COUNT(*) FROM selected) = (SELECT COUNT(*) FROM correct_options)
        INTO v_is_correct;
        
    ELSIF v_question_type = 'FILL_BLANK_TEXT' THEN
        -- Compare filled blanks with correct answers
        -- This is simplified; actual implementation would be more complex
        v_is_correct := true; -- Placeholder
        
    ELSE
        -- Cannot auto-grade
        RETURN false;
    END IF;
    
    -- Update answer with grading result
    UPDATE quiz_student_answers
    SET 
        is_correct = v_is_correct,
        points_earned = CASE WHEN v_is_correct THEN v_points ELSE 0 END
    WHERE id = p_answer_id;
    
    RETURN true;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate attempt score
CREATE OR REPLACE FUNCTION calculate_attempt_score(
    p_attempt_id BIGINT
) RETURNS void AS $$
DECLARE
    v_total_points DECIMAL(10,2);
    v_earned_points DECIMAL(10,2);
    v_percentage DECIMAL(5,2);
    v_passing_score DECIMAL(5,2);
    v_is_passed BOOLEAN;
BEGIN
    -- Sum up all points
    SELECT 
        SUM(qq.points),
        SUM(COALESCE(qsa.points_earned, 0))
    INTO v_total_points, v_earned_points
    FROM quiz_student_answers qsa
    JOIN quiz_questions qq ON qsa.question_id = qq.id
    WHERE qsa.attempt_id = p_attempt_id;
    
    -- Calculate percentage
    v_percentage := (v_earned_points / NULLIF(v_total_points, 0)) * 100;
    
    -- Check if passed
    SELECT passing_score INTO v_passing_score
    FROM quizzes q
    JOIN quiz_attempts qa ON q.id = qa.quiz_id
    WHERE qa.id = p_attempt_id;
    
    v_is_passed := v_percentage >= COALESCE(v_passing_score, 0);
    
    -- Update attempt
    UPDATE quiz_attempts
    SET 
        total_points = v_total_points,
        earned_points = v_earned_points,
        percentage = v_percentage,
        is_passed = v_is_passed,
        status = 'GRADED',
        updated_at = CURRENT_TIMESTAMP
    WHERE id = p_attempt_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- VIEWS FOR COMMON QUERIES
-- ============================================

-- View for quiz summary with statistics
CREATE OR REPLACE VIEW quiz_summary_view AS
SELECT 
    q.*,
    u.full_name as creator_name,
    u.email as creator_email,
    COUNT(DISTINCT qq.id) as question_count,
    COUNT(DISTINCT qa.id) as attempt_count,
    COUNT(DISTINCT qa.student_id) as student_count,
    AVG(qa.percentage) as average_score,
    COUNT(DISTINCT qa.id) FILTER (WHERE qa.is_passed = true) as passed_count
FROM quizzes q
LEFT JOIN users u ON q.created_by = u.id
LEFT JOIN quiz_questions qq ON q.id = qq.quiz_id
LEFT JOIN quiz_attempts qa ON q.id = qa.quiz_id AND qa.status = 'GRADED'
GROUP BY q.id, u.full_name, u.email;

-- View for student quiz attempts with details
CREATE OR REPLACE VIEW student_quiz_attempts_view AS
SELECT 
    qa.*,
    q.title as quiz_title,
    q.total_points as quiz_total_points,
    q.passing_score,
    u.full_name as student_name,
    u.email as student_email,
    COUNT(qsa.id) as answered_questions,
    COUNT(qsa.id) FILTER (WHERE qsa.is_correct = true) as correct_answers
FROM quiz_attempts qa
JOIN quizzes q ON qa.quiz_id = q.id
JOIN users u ON qa.student_id = u.id
LEFT JOIN quiz_student_answers qsa ON qa.id = qsa.attempt_id
GROUP BY qa.id, q.title, q.total_points, q.passing_score, u.full_name, u.email;

-- ============================================
-- INDEXES FOR JSONB QUERIES
-- ============================================

-- Index for answer_data JSONB queries
CREATE INDEX idx_student_answers_data ON quiz_student_answers USING gin(answer_data);
CREATE INDEX idx_quiz_questions_settings ON quiz_questions USING gin(settings);

-- ============================================
-- COMMENTS
-- ============================================

COMMENT ON TABLE quizzes IS 'Quiz configurations and settings';
COMMENT ON TABLE quiz_questions IS 'Questions within quizzes, supports multiple question types';
COMMENT ON TABLE quiz_answer_options IS 'Answer options for choice-based questions';
COMMENT ON TABLE quiz_correct_answers IS 'Correct answers for text/fill-in-the-blank questions';
COMMENT ON TABLE quiz_attempts IS 'Student attempts at quizzes';
COMMENT ON TABLE quiz_student_answers IS 'Student answers for individual questions';
COMMENT ON TABLE quiz_analytics IS 'Analytics data for quiz performance insights';