-- =============================================================
-- FLASHCARD DEDUPLICATION INDEXES
-- Prevents creating duplicate active flashcards for the same student+course+node/content and same front text.
-- =============================================================

CREATE UNIQUE INDEX IF NOT EXISTS uq_flashcard_student_node_front
ON flashcards (student_id, course_id, node_id, md5(front_text))
WHERE node_id IS NOT NULL AND status = 'ACTIVE';

-- Re-analyze flashcards table
ANALYZE flashcards;
