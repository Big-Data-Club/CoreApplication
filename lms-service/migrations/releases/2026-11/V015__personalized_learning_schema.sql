-- ══════════════════════════════════════════════════════════════════════════════
-- V015: Personalized Learning Engine Schema
-- ══════════════════════════════════════════════════════════════════════════════
-- Creates tables for skill-based personalization:
-- • Skills taxonomy and prerequisites
-- • Content-to-skill mappings
-- • Learning event tracking
-- • Learner skill state (mastery scores)
-- • Skill-based recommendations
-- ══════════════════════════════════════════════════════════════════════════════

-- ── SKILLS TAXONOMY ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS skills (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    parent_skill_id BIGINT REFERENCES skills(id) ON DELETE SET NULL,
    difficulty FLOAT CHECK (difficulty >= 0 AND difficulty <= 1),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name)
);

CREATE INDEX idx_skills_parent ON skills(parent_skill_id);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_skills_updated_at'
                   AND tgrelid='skills'::regclass) THEN
        CREATE TRIGGER update_skills_updated_at
            BEFORE UPDATE ON skills
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ── SKILL PREREQUISITES ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS skill_prerequisites (
    id BIGSERIAL PRIMARY KEY,
    skill_id BIGINT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    prerequisite_skill_id BIGINT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    strength FLOAT DEFAULT 1.0 CHECK (strength >= 0 AND strength <= 1),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(skill_id, prerequisite_skill_id),
    CHECK (skill_id != prerequisite_skill_id)
);

CREATE INDEX idx_skill_prerequisites_skill ON skill_prerequisites(skill_id);
CREATE INDEX idx_skill_prerequisites_prerequisite ON skill_prerequisites(prerequisite_skill_id);

-- ── CONTENT TO SKILLS MAPPING ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS content_skills (
    id BIGSERIAL PRIMARY KEY,
    content_id BIGINT NOT NULL REFERENCES section_content(id) ON DELETE CASCADE,
    skill_id BIGINT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    difficulty FLOAT CHECK (difficulty >= 0 AND difficulty <= 1),
    weight FLOAT DEFAULT 1.0 CHECK (weight >= 0 AND weight <= 1),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(content_id, skill_id)
);

CREATE INDEX idx_content_skills_content ON content_skills(content_id);
CREATE INDEX idx_content_skills_skill ON content_skills(skill_id);

-- ── QUIZ QUESTIONS TO SKILLS MAPPING ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS question_skills (
    id BIGSERIAL PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES quiz_questions(id) ON DELETE CASCADE,
    skill_id BIGINT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    difficulty FLOAT CHECK (difficulty >= 0 AND difficulty <= 1),
    weight FLOAT DEFAULT 1.0 CHECK (weight >= 0 AND weight <= 1),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(question_id, skill_id)
);

CREATE INDEX idx_question_skills_question ON question_skills(question_id);
CREATE INDEX idx_question_skills_skill ON question_skills(skill_id);

-- ── LEARNING EVENTS (Immutable Event Log) ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS learning_events (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(100) UNIQUE NOT NULL,
    event_type VARCHAR(50) NOT NULL CHECK (event_type IN (
        'lesson_opened', 'lesson_started', 'lesson_completed', 'lesson_abandoned', 'lesson_resumed',
        'question_viewed', 'answer_submitted', 'answer_retried',
        'hint_requested', 'recommendation_clicked'
    )),
    student_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id VARCHAR(100),
    course_id BIGINT REFERENCES courses(id) ON DELETE CASCADE,
    lesson_id BIGINT,
    question_id BIGINT REFERENCES quiz_questions(id) ON DELETE SET NULL,
    skill_id BIGINT REFERENCES skills(id) ON DELETE SET NULL,
    difficulty FLOAT CHECK (difficulty >= 0 AND difficulty <= 1),
    correct BOOLEAN,
    attempt_no INTEGER,
    response_time_ms BIGINT,
    hint_count INTEGER,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_learning_events_student ON learning_events(student_id, created_at DESC);
CREATE INDEX idx_learning_events_type ON learning_events(event_type, created_at DESC);
CREATE INDEX idx_learning_events_skill ON learning_events(skill_id, student_id);
CREATE INDEX idx_learning_events_course ON learning_events(course_id, student_id);
CREATE INDEX idx_learning_events_session ON learning_events(session_id);

-- ── LEARNER SKILL STATE (Materialized Mastery) ────────────────────────────────

CREATE TABLE IF NOT EXISTS learner_skill_states (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill_id BIGINT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    mastery_score FLOAT DEFAULT 0.0 CHECK (mastery_score >= 0 AND mastery_score <= 1),
    confidence_score FLOAT DEFAULT 0.0 CHECK (confidence_score >= 0 AND confidence_score <= 1),
    attempt_count INTEGER DEFAULT 0,
    accuracy FLOAT DEFAULT 0.0 CHECK (accuracy >= 0 AND accuracy <= 1),
    avg_response_time_ms BIGINT,
    hint_dependency FLOAT DEFAULT 0.0 CHECK (hint_dependency >= 0 AND hint_dependency <= 1),
    last_practiced_at TIMESTAMP,
    recommended_difficulty FLOAT CHECK (recommended_difficulty >= 0 AND recommended_difficulty <= 1),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, skill_id)
);

CREATE INDEX idx_learner_skill_states_student ON learner_skill_states(student_id, mastery_score DESC);
CREATE INDEX idx_learner_skill_states_skill ON learner_skill_states(skill_id, mastery_score DESC);
CREATE INDEX idx_learner_skill_states_mastery ON learner_skill_states(mastery_score);
CREATE INDEX idx_learner_skill_states_last_practiced ON learner_skill_states(last_practiced_at DESC);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_learner_skill_states_updated_at'
                   AND tgrelid='learner_skill_states'::regclass) THEN
        CREATE TRIGGER update_learner_skill_states_updated_at
            BEFORE UPDATE ON learner_skill_states
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ── SKILL RECOMMENDATIONS HISTORY ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS skill_recommendations (
    id BIGSERIAL PRIMARY KEY,
    recommendation_id VARCHAR(100) UNIQUE NOT NULL,
    student_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id BIGINT REFERENCES courses(id) ON DELETE SET NULL,
    content_id BIGINT REFERENCES section_content(id) ON DELETE SET NULL,
    skill_id BIGINT REFERENCES skills(id) ON DELETE SET NULL,
    difficulty FLOAT CHECK (difficulty >= 0 AND difficulty <= 1),
    reason VARCHAR(255),
    recommendation_score FLOAT CHECK (recommendation_score >= 0 AND recommendation_score <= 1),
    clicked BOOLEAN DEFAULT false,
    clicked_at TIMESTAMP,
    completed BOOLEAN DEFAULT false,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_skill_recommendations_student ON skill_recommendations(student_id, created_at DESC);
CREATE INDEX idx_skill_recommendations_recommendation_id ON skill_recommendations(recommendation_id);
CREATE INDEX idx_skill_recommendations_clicked ON skill_recommendations(clicked, created_at DESC);
CREATE INDEX idx_skill_recommendations_completed ON skill_recommendations(completed, created_at DESC);

-- ══════════════════════════════════════════════════════════════════════════════
-- End of V015
-- ══════════════════════════════════════════════════════════════════════════════
