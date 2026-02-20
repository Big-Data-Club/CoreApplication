-- Optional: Add settings column to quiz_answer_options if you want images on answer options
ALTER TABLE quiz_answer_options 
ADD COLUMN IF NOT EXISTS settings JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_answer_options_settings 
ON quiz_answer_options USING gin(settings);

-- Helper function to count images in a question
CREATE OR REPLACE FUNCTION count_question_images(question_settings JSONB)
RETURNS INTEGER AS $$
BEGIN
    RETURN jsonb_array_length(COALESCE(question_settings->'images', '[]'::jsonb));
END;
$$ LANGUAGE plpgsql IMMUTABLE;