-- V008__flashcard_lesson_id.sql
-- Allow flashcards to be generated directly from micro-lessons without knowledge nodes
ALTER TABLE flashcards ALTER COLUMN node_id DROP NOT NULL;
ALTER TABLE flashcards ADD COLUMN lesson_id BIGINT;
CREATE INDEX IF NOT EXISTS idx_fc_lesson ON flashcards(lesson_id);
