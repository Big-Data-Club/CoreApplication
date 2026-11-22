CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ── USERS ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id         BIGSERIAL PRIMARY KEY,
    email      VARCHAR(255) UNIQUE NOT NULL,
    full_name  VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_users_updated_at'
                   AND tgrelid='users'::regclass) THEN
        CREATE TRIGGER update_users_updated_at
            BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ── USER ROLES ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_roles (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       VARCHAR(50) NOT NULL CHECK (role IN ('STUDENT', 'TEACHER', 'ADMIN')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, role)
);

-- ── COURSES ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS courses (
    id            BIGSERIAL PRIMARY KEY,
    title         VARCHAR(255) NOT NULL,
    description   TEXT,
    category      VARCHAR(100),
    level         VARCHAR(50) CHECK (level IN ('BEGINNER','INTERMEDIATE','ADVANCED','ALL_LEVELS')),
    thumbnail_url VARCHAR(500),
    status        VARCHAR(50) DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','PUBLISHED','ARCHIVED')),
    created_by    BIGINT NOT NULL REFERENCES users(id),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at  TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_courses_updated_at'
                   AND tgrelid='courses'::regclass) THEN
        CREATE TRIGGER update_courses_updated_at
            BEFORE UPDATE ON courses
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ── COURSE SECTIONS ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS course_sections (
    id           BIGSERIAL PRIMARY KEY,
    course_id    BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title        VARCHAR(255) NOT NULL,
    description  TEXT,
    order_index  INTEGER NOT NULL,
    is_published BOOLEAN DEFAULT false,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_course_sections_updated_at'
                   AND tgrelid='course_sections'::regclass) THEN
        CREATE TRIGGER update_course_sections_updated_at
            BEFORE UPDATE ON course_sections
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ── SECTION CONTENT ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS section_content (
    id              BIGSERIAL PRIMARY KEY,
    section_id      BIGINT NOT NULL REFERENCES course_sections(id) ON DELETE CASCADE,
    type            VARCHAR(50) NOT NULL CHECK (type IN (
                        'TEXT','VIDEO','DOCUMENT','IMAGE','QUIZ','FORUM','ANNOUNCEMENT'
                    )),
    title           VARCHAR(255) NOT NULL,
    description     TEXT,
    order_index     INTEGER NOT NULL,
    metadata        JSONB,
    is_published    BOOLEAN DEFAULT false,
    is_mandatory    BOOLEAN DEFAULT false,
    file_path       VARCHAR(1000),
    file_size       BIGINT,
    file_type       VARCHAR(100),
    ai_index_status VARCHAR(20) DEFAULT 'not_indexed'
                        CHECK (ai_index_status IN ('not_indexed','processing','indexed','failed')),
    ai_index_job_id BIGINT,
    ai_indexed_at   TIMESTAMP,
    embedding_model VARCHAR(64) DEFAULT 'bge-m3',
    created_by      BIGINT NOT NULL REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_section_content_updated_at'
                   AND tgrelid='section_content'::regclass) THEN
        CREATE TRIGGER update_section_content_updated_at
            BEFORE UPDATE ON section_content
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ── ENROLLMENTS ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS enrollments (
    id          BIGSERIAL PRIMARY KEY,
    course_id   BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    student_id  BIGINT NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'ACCEPTED',
    enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rejected_at TIMESTAMP,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(course_id, student_id)
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_enrollments_updated_at'
                   AND tgrelid='enrollments'::regclass) THEN
        CREATE TRIGGER update_enrollments_updated_at
            BEFORE UPDATE ON enrollments
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

CREATE OR REPLACE FUNCTION auto_accept_enrollment()
RETURNS TRIGGER AS $$
BEGIN
    NEW.status      := 'ACCEPTED';
    NEW.accepted_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='trigger_auto_accept_enrollment'
                   AND tgrelid='enrollments'::regclass) THEN
        CREATE TRIGGER trigger_auto_accept_enrollment
            BEFORE INSERT ON enrollments
            FOR EACH ROW EXECUTE FUNCTION auto_accept_enrollment();
    END IF;
END $$;

-- ── BULK ENROLLMENT LOGS ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS bulk_enrollment_logs (
    id            BIGSERIAL PRIMARY KEY,
    course_id     BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    teacher_id    BIGINT NOT NULL,
    total_count   INT NOT NULL,
    success_count INT DEFAULT 0,
    failed_count  INT DEFAULT 0,
    status        VARCHAR(20) DEFAULT 'PROCESSING',
    error_message TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at  TIMESTAMP
);

-- ── QUIZZES ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS quizzes (
    id                       BIGSERIAL PRIMARY KEY,
    content_id               BIGINT NOT NULL REFERENCES section_content(id) ON DELETE CASCADE,
    title                    VARCHAR(500) NOT NULL,
    description              TEXT,
    instructions             TEXT,
    time_limit_minutes       INTEGER,
    available_from           TIMESTAMP,
    available_until          TIMESTAMP,
    max_attempts             INTEGER DEFAULT 1,
    shuffle_questions        BOOLEAN DEFAULT false,
    shuffle_answers          BOOLEAN DEFAULT false,
    passing_score            DECIMAL(5,2),
    total_points             DECIMAL(10,2) DEFAULT 100.00,
    auto_grade               BOOLEAN DEFAULT true,
    show_results_immediately BOOLEAN DEFAULT true,
    show_correct_answers     BOOLEAN DEFAULT true,
    allow_review             BOOLEAN DEFAULT true,
    show_feedback            BOOLEAN DEFAULT true,
    is_published             BOOLEAN DEFAULT false,
    created_by               BIGINT NOT NULL REFERENCES users(id),
    created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_quizzes_updated_at'
                   AND tgrelid='quizzes'::regclass) THEN
        CREATE TRIGGER update_quizzes_updated_at
            BEFORE UPDATE ON quizzes
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ── QUIZ QUESTIONS ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS quiz_questions (
    id            BIGSERIAL PRIMARY KEY,
    quiz_id       BIGINT NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    question_type VARCHAR(50) NOT NULL CHECK (question_type IN (
                      'SINGLE_CHOICE','MULTIPLE_CHOICE','SHORT_ANSWER','ESSAY',
                      'FILE_UPLOAD','FILL_BLANK_TEXT','FILL_BLANK_DROPDOWN'
                  )),
    question_text TEXT NOT NULL,
    question_html TEXT,
    explanation   TEXT,
    points        DECIMAL(10,2) DEFAULT 10.00,
    order_index   INTEGER NOT NULL,
    settings      JSONB DEFAULT '{}',
    is_required   BOOLEAN DEFAULT true,
    node_id       BIGINT,
    bloom_level   VARCHAR(20) CHECK (bloom_level IN
                      ('remember','understand','apply','analyze','evaluate','create')),
    reference_chunk_id BIGINT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_quiz_questions_updated_at'
                   AND tgrelid='quiz_questions'::regclass) THEN
        CREATE TRIGGER update_quiz_questions_updated_at
            BEFORE UPDATE ON quiz_questions
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ── QUIZ ANSWER OPTIONS ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS quiz_answer_options (
    id          BIGSERIAL PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES quiz_questions(id) ON DELETE CASCADE,
    option_text TEXT NOT NULL,
    option_html TEXT,
    is_correct  BOOLEAN DEFAULT false,
    order_index INTEGER NOT NULL,
    blank_id    INTEGER,
    settings    JSONB DEFAULT '{}',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── QUIZ CORRECT ANSWERS ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS quiz_correct_answers (
    id             BIGSERIAL PRIMARY KEY,
    question_id    BIGINT NOT NULL REFERENCES quiz_questions(id) ON DELETE CASCADE,
    answer_text    TEXT,
    blank_id       INTEGER,
    blank_position INTEGER,
    case_sensitive BOOLEAN DEFAULT false,
    exact_match    BOOLEAN DEFAULT false,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── QUIZ ATTEMPTS ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id                 BIGSERIAL PRIMARY KEY,
    quiz_id            BIGINT NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    student_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    attempt_number     INTEGER NOT NULL DEFAULT 1,
    started_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_at       TIMESTAMP,
    time_spent_seconds INTEGER,
    total_points       DECIMAL(10,2),
    earned_points      DECIMAL(10,2),
    percentage         DECIMAL(5,2),
    is_passed          BOOLEAN,
    status             VARCHAR(20) DEFAULT 'IN_PROGRESS' CHECK (status IN (
                           'IN_PROGRESS','SUBMITTED','GRADED','ABANDONED'
                       )),
    auto_graded_at     TIMESTAMP,
    manually_graded_at TIMESTAMP,
    graded_by          BIGINT REFERENCES users(id),
    ip_address         VARCHAR(45),
    user_agent         TEXT,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(quiz_id, student_id, attempt_number)
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_quiz_attempts_updated_at'
                   AND tgrelid='quiz_attempts'::regclass) THEN
        CREATE TRIGGER update_quiz_attempts_updated_at
            BEFORE UPDATE ON quiz_attempts
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ── QUIZ STUDENT ANSWERS ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS quiz_student_answers (
    id                 BIGSERIAL PRIMARY KEY,
    attempt_id         BIGINT NOT NULL REFERENCES quiz_attempts(id) ON DELETE CASCADE,
    question_id        BIGINT NOT NULL REFERENCES quiz_questions(id) ON DELETE CASCADE,
    answer_data        JSONB NOT NULL,
    points_earned      DECIMAL(10,2),
    is_correct         BOOLEAN,
    grader_feedback    TEXT,
    graded_by          BIGINT REFERENCES users(id),
    graded_at          TIMESTAMP,
    answered_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    time_spent_seconds INTEGER,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(attempt_id, question_id)
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_quiz_student_answers_updated_at'
                   AND tgrelid='quiz_student_answers'::regclass) THEN
        CREATE TRIGGER update_quiz_student_answers_updated_at
            BEFORE UPDATE ON quiz_student_answers
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ── QUIZ ANALYTICS ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS quiz_analytics (
    id                BIGSERIAL PRIMARY KEY,
    quiz_id           BIGINT NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    question_id       BIGINT REFERENCES quiz_questions(id) ON DELETE CASCADE,
    total_attempts    INTEGER DEFAULT 0,
    correct_count     INTEGER DEFAULT 0,
    incorrect_count   INTEGER DEFAULT 0,
    average_score     DECIMAL(5,2),
    difficulty_rating VARCHAR(20),
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(quiz_id, question_id)
);

-- ── CONTENT PROGRESS ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS content_progress (
    id           BIGSERIAL PRIMARY KEY,
    content_id   BIGINT NOT NULL REFERENCES section_content(id) ON DELETE CASCADE,
    student_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(content_id, student_id)
);

-- ── HELPER FUNCTIONS ──────────────────────────────────────────

CREATE OR REPLACE FUNCTION count_question_blanks(question_text TEXT)
RETURNS INTEGER AS $$
DECLARE blank_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO blank_count
    FROM regexp_matches(question_text, '\{BLANK_\d+\}', 'g');
    RETURN COALESCE(blank_count, 0);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION calculate_attempt_score(p_attempt_id BIGINT)
RETURNS void AS $$
DECLARE
    v_total_points  DECIMAL(10,2);
    v_earned_points DECIMAL(10,2);
    v_percentage    DECIMAL(5,2);
    v_passing_score DECIMAL(5,2);
BEGIN
    SELECT SUM(qq.points), SUM(COALESCE(qsa.points_earned, 0))
    INTO   v_total_points, v_earned_points
    FROM   quiz_student_answers qsa
    JOIN   quiz_questions qq ON qsa.question_id = qq.id
    WHERE  qsa.attempt_id = p_attempt_id;

    v_percentage := (v_earned_points / NULLIF(v_total_points, 0)) * 100;

    SELECT q.passing_score INTO v_passing_score
    FROM   quizzes q JOIN quiz_attempts qa ON q.id = qa.quiz_id
    WHERE  qa.id = p_attempt_id;

    UPDATE quiz_attempts
    SET    total_points  = v_total_points,
           earned_points = v_earned_points,
           percentage    = v_percentage,
           is_passed     = (v_percentage >= COALESCE(v_passing_score, 0)),
           status        = 'GRADED',
           updated_at    = CURRENT_TIMESTAMP
    WHERE  id = p_attempt_id;
END;
$$ LANGUAGE plpgsql;

-- ── FORUM POSTS ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS forum_posts (
    id            BIGSERIAL PRIMARY KEY,
    content_id    BIGINT NOT NULL REFERENCES section_content(id) ON DELETE CASCADE,
    user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title         VARCHAR(255) NOT NULL,
    body          TEXT NOT NULL,
    tags          VARCHAR(100)[] DEFAULT '{}',
    upvotes       INTEGER DEFAULT 0,
    downvotes     INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    view_count    INTEGER DEFAULT 0,
    is_pinned     BOOLEAN DEFAULT false,
    is_locked     BOOLEAN DEFAULT false,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_forum_posts_updated_at'
                   AND tgrelid='forum_posts'::regclass) THEN
        CREATE TRIGGER update_forum_posts_updated_at
            BEFORE UPDATE ON forum_posts
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS forum_comments (
    id                BIGSERIAL PRIMARY KEY,
    post_id           BIGINT NOT NULL REFERENCES forum_posts(id) ON DELETE CASCADE,
    parent_comment_id BIGINT REFERENCES forum_comments(id) ON DELETE CASCADE,
    user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body              TEXT NOT NULL,
    upvotes           INTEGER DEFAULT 0,
    downvotes         INTEGER DEFAULT 0,
    is_accepted       BOOLEAN DEFAULT false,
    depth             INTEGER DEFAULT 0,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_forum_comments_updated_at'
                   AND tgrelid='forum_comments'::regclass) THEN
        CREATE TRIGGER update_forum_comments_updated_at
            BEFORE UPDATE ON forum_comments
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS forum_votes (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    votable_type VARCHAR(20) NOT NULL CHECK (votable_type IN ('post', 'comment')),
    votable_id   BIGINT NOT NULL,
    vote_type    VARCHAR(10) NOT NULL CHECK (vote_type IN ('upvote', 'downvote')),
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, votable_type, votable_id)
);

CREATE OR REPLACE FUNCTION update_post_comment_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE forum_posts SET comment_count = comment_count + 1 WHERE id = NEW.post_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE forum_posts SET comment_count = comment_count - 1 WHERE id = OLD.post_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='trigger_update_post_comment_count'
                   AND tgrelid='forum_comments'::regclass) THEN
        CREATE TRIGGER trigger_update_post_comment_count
            AFTER INSERT OR DELETE ON forum_comments
            FOR EACH ROW EXECUTE FUNCTION update_post_comment_count();
    END IF;
END $$;

CREATE OR REPLACE FUNCTION update_vote_counts()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.votable_type = 'post' THEN
            IF NEW.vote_type = 'upvote' THEN UPDATE forum_posts SET upvotes   = upvotes   + 1 WHERE id = NEW.votable_id;
            ELSE                              UPDATE forum_posts SET downvotes = downvotes + 1 WHERE id = NEW.votable_id; END IF;
        ELSE
            IF NEW.vote_type = 'upvote' THEN UPDATE forum_comments SET upvotes   = upvotes   + 1 WHERE id = NEW.votable_id;
            ELSE                              UPDATE forum_comments SET downvotes = downvotes + 1 WHERE id = NEW.votable_id; END IF;
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        IF OLD.votable_type = 'post' THEN
            IF OLD.vote_type = 'upvote' THEN UPDATE forum_posts SET upvotes   = upvotes   - 1 WHERE id = OLD.votable_id;
            ELSE                              UPDATE forum_posts SET downvotes = downvotes - 1 WHERE id = OLD.votable_id; END IF;
        ELSE
            IF OLD.vote_type = 'upvote' THEN UPDATE forum_comments SET upvotes   = upvotes   - 1 WHERE id = OLD.votable_id;
            ELSE                              UPDATE forum_comments SET downvotes = downvotes - 1 WHERE id = OLD.votable_id; END IF;
        END IF;
    ELSIF TG_OP = 'UPDATE' AND OLD.vote_type <> NEW.vote_type THEN
        IF NEW.votable_type = 'post' THEN
            IF NEW.vote_type = 'upvote' THEN UPDATE forum_posts SET upvotes = upvotes + 1, downvotes = downvotes - 1 WHERE id = NEW.votable_id;
            ELSE                             UPDATE forum_posts SET upvotes = upvotes - 1, downvotes = downvotes + 1 WHERE id = NEW.votable_id; END IF;
        ELSE
            IF NEW.vote_type = 'upvote' THEN UPDATE forum_comments SET upvotes = upvotes + 1, downvotes = downvotes - 1 WHERE id = NEW.votable_id;
            ELSE                             UPDATE forum_comments SET upvotes = upvotes - 1, downvotes = downvotes + 1 WHERE id = NEW.votable_id; END IF;
        END IF;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='trigger_update_vote_counts'
                   AND tgrelid='forum_votes'::regclass) THEN
        CREATE TRIGGER trigger_update_vote_counts
            AFTER INSERT OR UPDATE OR DELETE ON forum_votes
            FOR EACH ROW EXECUTE FUNCTION update_vote_counts();
    END IF;
END $$;

-- ── MICRO LESSONS ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS micro_lesson_jobs (
    id                BIGSERIAL PRIMARY KEY,
    course_id         BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    section_id        BIGINT REFERENCES course_sections(id) ON DELETE SET NULL,
    source_content_id BIGINT REFERENCES section_content(id) ON DELETE SET NULL,
    source_file_path  VARCHAR(1000),
    source_file_type  VARCHAR(100),
    source_url        VARCHAR(1000),
    target_minutes    INT NOT NULL DEFAULT 5,
    language          VARCHAR(10) NOT NULL DEFAULT 'vi',
    status            VARCHAR(20) NOT NULL DEFAULT 'queued'
                          CHECK (status IN ('queued','processing','completed','failed')),
    progress          INT DEFAULT 0,
    stage             VARCHAR(64) DEFAULT '',
    lessons_count     INT DEFAULT 0,
    error             TEXT,
    created_by        BIGINT NOT NULL REFERENCES users(id),
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at      TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_micro_lesson_jobs_updated_at'
                   AND tgrelid='micro_lesson_jobs'::regclass) THEN
        CREATE TRIGGER update_micro_lesson_jobs_updated_at
            BEFORE UPDATE ON micro_lesson_jobs
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS micro_lessons (
    id                  BIGSERIAL PRIMARY KEY,
    job_id              BIGINT NOT NULL REFERENCES micro_lesson_jobs(id) ON DELETE CASCADE,
    course_id           BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    section_id          BIGINT REFERENCES course_sections(id) ON DELETE SET NULL,
    source_content_id   BIGINT REFERENCES section_content(id) ON DELETE SET NULL,
    title               VARCHAR(500) NOT NULL,
    summary             TEXT,
    objectives          JSONB DEFAULT '[]'::jsonb,
    markdown_content    TEXT NOT NULL,
    estimated_minutes   INT DEFAULT 5,
    order_index         INT NOT NULL DEFAULT 0,
    status              VARCHAR(20) NOT NULL DEFAULT 'draft'
                            CHECK (status IN ('draft','published','archived')),
    published_content_id BIGINT REFERENCES section_content(id) ON DELETE SET NULL,
    image_urls          JSONB DEFAULT '[]'::jsonb,
    language            VARCHAR(10) DEFAULT 'vi',
    node_id             BIGINT,
    created_by          BIGINT NOT NULL REFERENCES users(id),
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at        TIMESTAMP
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='update_micro_lessons_updated_at'
                   AND tgrelid='micro_lessons'::regclass) THEN
        CREATE TRIGGER update_micro_lessons_updated_at
            BEFORE UPDATE ON micro_lessons
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ── MICRO-LESSON INTERACTIONS ────────────────────────────────────

CREATE TABLE IF NOT EXISTS micro_lesson_interactions (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id       BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    lesson_id       BIGINT REFERENCES micro_lessons(id) ON DELETE SET NULL,
    node_id         BIGINT,
    action_type     VARCHAR(40) NOT NULL
                       CHECK (action_type IN (
                            'lesson_view',
                            'lesson_complete',
                            'flashcard_flip',
                            'flashcard_rate',
                            'quick_check_attempt',
                            'quick_check_correct',
                            'quick_check_incorrect',
                            'ask_ai'
                       )),
    score           DOUBLE PRECISION,
    status          VARCHAR(40),
    payload         JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ── KNOWLEDGE NODE MASTERY ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS knowledge_node_mastery (
    user_id              BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id            BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    node_id              BIGINT NOT NULL,
    formal_quiz_score    DOUBLE PRECISION NOT NULL DEFAULT 0,
    formal_quiz_count    INT              NOT NULL DEFAULT 0,
    mini_quiz_score      DOUBLE PRECISION NOT NULL DEFAULT 0,
    mini_quiz_count      INT              NOT NULL DEFAULT 0,
    completion_score     DOUBLE PRECISION NOT NULL DEFAULT 0,
    completion_count     INT              NOT NULL DEFAULT 0,
    engagement_score     DOUBLE PRECISION NOT NULL DEFAULT 0,
    engagement_count     INT              NOT NULL DEFAULT 0,
    mastery_level        DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_interaction_at  TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, course_id, node_id)
);

-- ── AI INDEX STATUS RESET TRIGGER ────────────────────────────

CREATE OR REPLACE FUNCTION reset_ai_index_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.ai_index_status = 'processing' AND OLD.ai_index_status <> 'processing' THEN
        NEW.ai_indexed_at   := NULL;
        NEW.ai_index_job_id := NULL;
    END IF;
    IF NEW.ai_index_status = 'indexed' THEN
        NEW.ai_indexed_at := CURRENT_TIMESTAMP;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 'trigger_reset_ai_index_timestamp'
                     AND tgrelid = 'section_content'::regclass) THEN
        CREATE TRIGGER trigger_reset_ai_index_timestamp
            BEFORE UPDATE OF ai_index_status ON section_content
            FOR EACH ROW EXECUTE FUNCTION reset_ai_index_timestamp();
    END IF;
END $$;

-- ── VIEWS ─────────────────────────────────────────────────────

CREATE OR REPLACE VIEW v_content_ai_status AS
SELECT
    sc.id               AS content_id,
    sc.title,
    sc.type,
    sc.ai_index_status,
    sc.ai_indexed_at,
    sc.embedding_model,
    cs.course_id,
    c.title             AS course_title
FROM section_content sc
JOIN course_sections cs ON cs.id = sc.section_id
JOIN courses         c  ON c.id  = cs.course_id
WHERE sc.type NOT IN ('QUIZ', 'FORUM', 'ANNOUNCEMENT')
ORDER BY sc.ai_index_status, sc.updated_at DESC;

CREATE OR REPLACE VIEW quiz_summary_view AS
SELECT
    q.*,
    u.full_name                                                  AS creator_name,
    u.email                                                      AS creator_email,
    COUNT(DISTINCT qq.id)                                        AS question_count,
    COUNT(DISTINCT qa.id)                                        AS attempt_count,
    COUNT(DISTINCT qa.student_id)                                AS student_count,
    AVG(qa.percentage)                                           AS average_score,
    COUNT(DISTINCT qa.id) FILTER (WHERE qa.is_passed = true)     AS passed_count
FROM       quizzes q
LEFT JOIN  users           u  ON q.created_by = u.id
LEFT JOIN  quiz_questions  qq ON q.id = qq.quiz_id
LEFT JOIN  quiz_attempts   qa ON q.id = qa.quiz_id AND qa.status = 'GRADED'
GROUP BY   q.id, u.full_name, u.email;
