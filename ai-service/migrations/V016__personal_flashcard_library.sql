-- Personal library is owned by AI, like the existing flashcard/repetition data.
CREATE TABLE personal_flashcard_decks (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL,
    name VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON personal_flashcard_decks(student_id);
CREATE TABLE personal_flashcards (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL,
    deck_id BIGINT NOT NULL REFERENCES personal_flashcard_decks(id) ON DELETE CASCADE,
    front_text TEXT NOT NULL,
    back_text TEXT NOT NULL,
    accepted_answers JSONB NOT NULL DEFAULT '[]',
    note TEXT NOT NULL DEFAULT '',
    language VARCHAR(35) NOT NULL DEFAULT 'vi-VN',
    answer_language VARCHAR(35) NOT NULL DEFAULT 'vi-VN',
    match_mode VARCHAR(10) NOT NULL DEFAULT 'exact' CHECK (match_mode IN ('exact', 'ai')),
    case_sensitive BOOLEAN NOT NULL DEFAULT false,
    repetitions INTEGER NOT NULL DEFAULT 0,
    interval_days INTEGER NOT NULL DEFAULT 0,
    easiness DOUBLE PRECISION NOT NULL DEFAULT 2.5,
    due_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revision INTEGER NOT NULL DEFAULT 1,
    legacy_id BIGINT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON personal_flashcards(student_id, deck_id, due_at);
CREATE TABLE personal_flashcard_reviews (
    id UUID PRIMARY KEY,
    student_id BIGINT NOT NULL,
    card_id BIGINT NOT NULL REFERENCES personal_flashcards(id) ON DELETE CASCADE,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE personal_flashcard_jobs (
    id UUID PRIMARY KEY,
    student_id BIGINT NOT NULL,
    kind VARCHAR(10) NOT NULL CHECK (kind IN ('generate', 'check')),
    status VARCHAR(12) NOT NULL DEFAULT 'pending',
    payload JSONB NOT NULL,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON personal_flashcard_jobs(student_id, created_at);
-- Preserve existing personal cards and review schedules without node dependencies.
INSERT INTO personal_flashcard_decks(student_id, name)
SELECT DISTINCT student_id, 'Thẻ đã lưu' FROM flashcards WHERE status = 'ACTIVE';
INSERT INTO personal_flashcards(student_id, deck_id, front_text, back_text, legacy_id,
    repetitions, interval_days, easiness, due_at)
SELECT f.student_id, d.id, f.front_text, f.back_text, f.id,
    COALESCE(r.repetitions, 0), COALESCE(r.interval_days, 0), COALESCE(r.easiness_factor, 2.5),
    COALESCE(r.next_review_date::timestamptz, now())
FROM flashcards f JOIN personal_flashcard_decks d ON d.student_id = f.student_id
LEFT JOIN flashcard_repetitions r ON r.flashcard_id = f.id AND r.student_id = f.student_id
WHERE f.status = 'ACTIVE';
