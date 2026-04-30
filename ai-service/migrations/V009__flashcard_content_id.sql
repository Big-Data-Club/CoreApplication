-- V009__flashcard_content_id.sql
ALTER TABLE flashcards ADD COLUMN content_id BIGINT;
CREATE INDEX idx_flashcards_content_id ON flashcards(content_id);
