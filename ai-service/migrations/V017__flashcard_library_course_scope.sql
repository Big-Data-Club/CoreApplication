-- V016 may already be deployed. Extend it without rewriting its history.
ALTER TABLE personal_flashcard_decks ADD COLUMN course_id BIGINT;
ALTER TABLE personal_flashcard_jobs ADD COLUMN course_id BIGINT;
CREATE INDEX ON personal_flashcard_decks(student_id, course_id);
CREATE INDEX ON personal_flashcard_jobs(student_id, course_id, created_at);

-- V016 combined legacy cards by learner. Split each deck using the source
-- course while preserving card IDs, edits, reviews and repetition schedules.
DO $$
DECLARE source RECORD; target_id BIGINT;
BEGIN
    FOR source IN
        SELECT DISTINCT d.id AS deck_id, d.student_id, d.name, f.course_id
        FROM personal_flashcard_decks d
        JOIN personal_flashcards c ON c.deck_id = d.id
        JOIN flashcards f ON f.id = c.legacy_id AND f.student_id = c.student_id
        WHERE d.course_id IS NULL AND f.course_id IS NOT NULL
    LOOP
        INSERT INTO personal_flashcard_decks(student_id, name, course_id)
        VALUES(source.student_id, source.name, source.course_id) RETURNING id INTO target_id;
        UPDATE personal_flashcards c SET deck_id = target_id
        FROM flashcards f
        WHERE c.deck_id = source.deck_id AND c.legacy_id = f.id
          AND c.student_id = source.student_id AND f.course_id = source.course_id;
    END LOOP;
END $$;

-- Existing user-created cards without a course stay private and can be moved
-- explicitly into an accessible course by their owner. Do not guess a course.
-- Old in-flight AI checks can recover their scope through their card.
UPDATE personal_flashcard_jobs j SET course_id = d.course_id
FROM personal_flashcards c JOIN personal_flashcard_decks d ON d.id = c.deck_id
WHERE j.kind = 'check' AND j.student_id = c.student_id
  AND (j.payload->>'card_id')::BIGINT = c.id;
UPDATE personal_flashcard_jobs SET status='failed',
    error='Hãy chọn khóa học và tạo lại yêu cầu.', updated_at=now()
WHERE course_id IS NULL AND status IN ('pending', 'processing');
