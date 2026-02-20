-- ============================================
-- FILL BLANK QUESTIONS SUPPORT
-- ============================================
-- Migration để đảm bảo database hỗ trợ đầy đủ cho 2 loại câu hỏi điền vào chỗ trống
-- Chạy file này nếu bạn gặp vấn đề với fill blank questions

-- 1. Đảm bảo settings column có kiểu JSONB
-- (Đã có trong bảng quiz_questions từ migration gốc)

-- 2. Đảm bảo quiz_answer_options có cột settings (cho dropdown images nếu cần)
ALTER TABLE quiz_answer_options 
ADD COLUMN IF NOT EXISTS settings JSONB DEFAULT '{}'::jsonb;

-- 3. Tạo index cho settings nếu chưa có
CREATE INDEX IF NOT EXISTS idx_question_settings 
ON quiz_questions USING gin(settings);

CREATE INDEX IF NOT EXISTS idx_answer_options_settings 
ON quiz_answer_options USING gin(settings);

-- 4. Tạo index cho blank_id trong answer_options (để query nhanh hơn)
CREATE INDEX IF NOT EXISTS idx_answer_options_blank_id 
ON quiz_answer_options (blank_id) 
WHERE blank_id IS NOT NULL;

-- 5. Tạo index cho blank_id trong correct_answers (để query nhanh hơn)
CREATE INDEX IF NOT EXISTS idx_correct_answers_blank_id 
ON quiz_correct_answers (blank_id) 
WHERE blank_id IS NOT NULL;

-- 6. Helper function để count blanks trong một question
CREATE OR REPLACE FUNCTION count_question_blanks(question_text TEXT)
RETURNS INTEGER AS $$
DECLARE
    blank_count INTEGER;
BEGIN
    -- Đếm số lần xuất hiện của pattern {BLANK_X}
    SELECT COUNT(*)
    INTO blank_count
    FROM regexp_matches(question_text, '\{BLANK_\d+\}', 'g');
    
    RETURN COALESCE(blank_count, 0);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 7. Helper function để extract blank IDs từ question text
CREATE OR REPLACE FUNCTION extract_blank_ids(question_text TEXT)
RETURNS INTEGER[] AS $$
DECLARE
    blank_ids INTEGER[];
    matches TEXT[];
    blank_id INTEGER;
BEGIN
    -- Extract tất cả {BLANK_X} patterns
    SELECT array_agg(match[1])
    INTO matches
    FROM regexp_matches(question_text, '\{BLANK_(\d+)\}', 'g') AS match;
    
    IF matches IS NULL THEN
        RETURN ARRAY[]::INTEGER[];
    END IF;
    
    -- Convert sang array of integers
    SELECT array_agg(DISTINCT match::INTEGER ORDER BY match::INTEGER)
    INTO blank_ids
    FROM unnest(matches) AS match;
    
    RETURN COALESCE(blank_ids, ARRAY[]::INTEGER[]);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 8. Validation function cho Fill Blank Text questions
CREATE OR REPLACE FUNCTION validate_fill_blank_text_question(
    question_id BIGINT
)
RETURNS TABLE (
    is_valid BOOLEAN,
    error_message TEXT
) AS $$
DECLARE
    q_text TEXT;
    q_settings JSONB;
    blank_count INTEGER;
    expected_blank_count INTEGER;
    blank_ids INTEGER[];
    missing_answers INTEGER[];
BEGIN
    -- Get question data
    SELECT question_text, settings
    INTO q_text, q_settings
    FROM quiz_questions
    WHERE id = question_id AND question_type = 'FILL_BLANK_TEXT';
    
    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'Question not found or not FILL_BLANK_TEXT type';
        RETURN;
    END IF;
    
    -- Count blanks in text
    blank_count := count_question_blanks(q_text);
    expected_blank_count := (q_settings->>'blank_count')::INTEGER;
    
    IF blank_count = 0 THEN
        RETURN QUERY SELECT FALSE, 'No blanks found in question text';
        RETURN;
    END IF;
    
    IF blank_count != expected_blank_count THEN
        RETURN QUERY SELECT FALSE, format('Blank count mismatch: found %s, expected %s', blank_count, expected_blank_count);
        RETURN;
    END IF;
    
    -- Check if each blank has at least one correct answer
    blank_ids := extract_blank_ids(q_text);
    
    SELECT array_agg(blank_id)
    INTO missing_answers
    FROM unnest(blank_ids) AS blank_id
    WHERE NOT EXISTS (
        SELECT 1
        FROM quiz_correct_answers
        WHERE question_id = validate_fill_blank_text_question.question_id
        AND blank_id = blank_id
        AND answer_text IS NOT NULL
        AND answer_text != ''
    );
    
    IF missing_answers IS NOT NULL AND array_length(missing_answers, 1) > 0 THEN
        RETURN QUERY SELECT FALSE, format('Missing correct answers for blanks: %s', array_to_string(missing_answers, ', '));
        RETURN;
    END IF;
    
    -- All validations passed
    RETURN QUERY SELECT TRUE, 'Valid'::TEXT;
END;
$$ LANGUAGE plpgsql;

-- 9. Validation function cho Fill Blank Dropdown questions
CREATE OR REPLACE FUNCTION validate_fill_blank_dropdown_question(
    question_id BIGINT
)
RETURNS TABLE (
    is_valid BOOLEAN,
    error_message TEXT
) AS $$
DECLARE
    q_text TEXT;
    q_settings JSONB;
    blank_count INTEGER;
    expected_blank_count INTEGER;
    blank_ids INTEGER[];
    blank_id INTEGER;
    option_count INTEGER;
    correct_count INTEGER;
BEGIN
    -- Get question data
    SELECT question_text, settings
    INTO q_text, q_settings
    FROM quiz_questions
    WHERE id = question_id AND question_type = 'FILL_BLANK_DROPDOWN';
    
    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'Question not found or not FILL_BLANK_DROPDOWN type';
        RETURN;
    END IF;
    
    -- Count blanks in text
    blank_count := count_question_blanks(q_text);
    expected_blank_count := (q_settings->>'blank_count')::INTEGER;
    
    IF blank_count = 0 THEN
        RETURN QUERY SELECT FALSE, 'No blanks found in question text';
        RETURN;
    END IF;
    
    IF blank_count != expected_blank_count THEN
        RETURN QUERY SELECT FALSE, format('Blank count mismatch: found %s, expected %s', blank_count, expected_blank_count);
        RETURN;
    END IF;
    
    -- Check each blank has at least 2 options and exactly 1 correct answer
    blank_ids := extract_blank_ids(q_text);
    
    FOREACH blank_id IN ARRAY blank_ids LOOP
        -- Count options for this blank
        SELECT COUNT(*)
        INTO option_count
        FROM quiz_answer_options
        WHERE question_id = validate_fill_blank_dropdown_question.question_id
        AND blank_id = blank_id;
        
        IF option_count < 2 THEN
            RETURN QUERY SELECT FALSE, format('Blank %s has less than 2 options (%s found)', blank_id, option_count);
            RETURN;
        END IF;
        
        -- Count correct options for this blank
        SELECT COUNT(*)
        INTO correct_count
        FROM quiz_answer_options
        WHERE question_id = validate_fill_blank_dropdown_question.question_id
        AND blank_id = blank_id
        AND is_correct = TRUE;
        
        IF correct_count = 0 THEN
            RETURN QUERY SELECT FALSE, format('Blank %s has no correct answer', blank_id);
            RETURN;
        END IF;
        
        IF correct_count > 1 THEN
            RETURN QUERY SELECT FALSE, format('Blank %s has multiple correct answers (%s found)', blank_id, correct_count);
            RETURN;
        END IF;
    END LOOP;
    
    -- All validations passed
    RETURN QUERY SELECT TRUE, 'Valid'::TEXT;
END;
$$ LANGUAGE plpgsql;

-- 10. Convenience view để xem tất cả fill blank questions với validation status
CREATE OR REPLACE VIEW v_fill_blank_questions_status AS
SELECT 
    q.id,
    q.quiz_id,
    q.question_type,
    q.question_text,
    q.settings,
    count_question_blanks(q.question_text) AS detected_blank_count,
    (q.settings->>'blank_count')::INTEGER AS expected_blank_count,
    CASE 
        WHEN q.question_type = 'FILL_BLANK_TEXT' THEN
            (SELECT is_valid FROM validate_fill_blank_text_question(q.id))
        WHEN q.question_type = 'FILL_BLANK_DROPDOWN' THEN
            (SELECT is_valid FROM validate_fill_blank_dropdown_question(q.id))
        ELSE NULL
    END AS is_valid,
    CASE 
        WHEN q.question_type = 'FILL_BLANK_TEXT' THEN
            (SELECT error_message FROM validate_fill_blank_text_question(q.id))
        WHEN q.question_type = 'FILL_BLANK_DROPDOWN' THEN
            (SELECT error_message FROM validate_fill_blank_dropdown_question(q.id))
        ELSE NULL
    END AS validation_message
FROM quiz_questions q
WHERE q.question_type IN ('FILL_BLANK_TEXT', 'FILL_BLANK_DROPDOWN');

-- Usage examples:
-- SELECT * FROM v_fill_blank_questions_status WHERE is_valid = FALSE;
-- SELECT * FROM validate_fill_blank_text_question(123);
-- SELECT count_question_blanks('This is {BLANK_1} a {BLANK_2} test');
-- SELECT extract_blank_ids('Fill {BLANK_1} and {BLANK_3} and {BLANK_2}');