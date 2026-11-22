-- Additive upgrade for installations that already applied V016/V017.
ALTER TABLE personal_flashcard_jobs DROP CONSTRAINT personal_flashcard_jobs_kind_check;
ALTER TABLE personal_flashcard_jobs ADD CONSTRAINT personal_flashcard_jobs_kind_check
    CHECK (kind IN ('generate', 'check', 'content', 'quiz'));
ALTER TABLE personal_flashcard_decks ADD COLUMN source_content_id BIGINT;
ALTER TABLE personal_flashcard_decks ADD COLUMN source_lesson_id BIGINT;
CREATE UNIQUE INDEX personal_deck_content ON personal_flashcard_decks(student_id, course_id, source_content_id)
    WHERE source_content_id IS NOT NULL;
CREATE UNIQUE INDEX personal_deck_lesson ON personal_flashcard_decks(student_id, course_id, source_lesson_id)
    WHERE source_lesson_id IS NOT NULL;
ALTER TABLE personal_flashcards ADD COLUMN source_node_ids JSONB NOT NULL DEFAULT '[]'::jsonb;
