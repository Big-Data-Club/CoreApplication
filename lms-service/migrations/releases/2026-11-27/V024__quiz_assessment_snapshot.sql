-- Preserve assessment attribution when teachers subsequently edit a question.
ALTER TABLE quiz_student_answers ADD COLUMN IF NOT EXISTS assessed_node_id BIGINT;
ALTER TABLE quiz_student_answers ADD COLUMN IF NOT EXISTS assessed_max_points NUMERIC;
ALTER TABLE quiz_student_answers ADD COLUMN IF NOT EXISTS assessment_snapshot_origin TEXT;
UPDATE quiz_student_answers a SET assessed_node_id=q.node_id,
    assessed_max_points=q.points, assessment_snapshot_origin='backfill_current'
FROM quiz_questions q WHERE q.id=a.question_id AND a.assessment_snapshot_origin IS NULL;

CREATE OR REPLACE FUNCTION capture_quiz_assessment_snapshot() RETURNS TRIGGER AS $$
BEGIN
    SELECT node_id,points INTO NEW.assessed_node_id,NEW.assessed_max_points
    FROM quiz_questions WHERE id=NEW.question_id;
    NEW.assessment_snapshot_origin := 'at_answer';
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='quiz_answer_assessment_snapshot' AND tgrelid='quiz_student_answers'::regclass) THEN
  CREATE TRIGGER quiz_answer_assessment_snapshot BEFORE INSERT ON quiz_student_answers
  FOR EACH ROW EXECUTE FUNCTION capture_quiz_assessment_snapshot();
 END IF;
END $$;
CREATE INDEX IF NOT EXISTS quiz_questions_index_cursor ON quiz_questions(quiz_id,id);

-- O(1) freshness checks, independent of quiz size and authoring entry point.
CREATE TABLE IF NOT EXISTS quiz_index_versions (
 quiz_id BIGINT PRIMARY KEY REFERENCES quizzes(id) ON DELETE CASCADE,
 revision BIGINT NOT NULL DEFAULT 1,
 question_count BIGINT NOT NULL DEFAULT 0 CHECK(question_count>=0)
);

CREATE OR REPLACE FUNCTION touch_quiz_index(quiz BIGINT,delta INTEGER) RETURNS VOID AS $$
 INSERT INTO quiz_index_versions(quiz_id,question_count)
 SELECT id,GREATEST(0,delta) FROM quizzes WHERE id=quiz
 ON CONFLICT(quiz_id) DO UPDATE SET revision=quiz_index_versions.revision+1,
 question_count=GREATEST(0,quiz_index_versions.question_count+delta);
$$ LANGUAGE SQL;

CREATE OR REPLACE FUNCTION track_quiz_question_index() RETURNS TRIGGER AS $$
BEGIN
 IF TG_OP='INSERT' THEN PERFORM touch_quiz_index(NEW.quiz_id,1);
 ELSIF TG_OP='DELETE' THEN PERFORM touch_quiz_index(OLD.quiz_id,-1);
 ELSIF NEW.quiz_id IS DISTINCT FROM OLD.quiz_id THEN
  PERFORM touch_quiz_index(OLD.quiz_id,-1); PERFORM touch_quiz_index(NEW.quiz_id,1);
 ELSIF ROW(NEW.question_text,NEW.points,NEW.node_id) IS DISTINCT FROM ROW(OLD.question_text,OLD.points,OLD.node_id) THEN
  PERFORM touch_quiz_index(NEW.quiz_id,0);
 END IF;
 RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION track_quiz_option_index() RETURNS TRIGGER AS $$
DECLARE quiz BIGINT;
BEGIN
 IF TG_OP<>'INSERT' THEN
  SELECT quiz_id INTO quiz FROM quiz_questions WHERE id=OLD.question_id;
  IF quiz IS NOT NULL THEN PERFORM touch_quiz_index(quiz,0); END IF;
 END IF;
 IF TG_OP='INSERT' OR (TG_OP='UPDATE' AND NEW.question_id IS DISTINCT FROM OLD.question_id) THEN
  SELECT quiz_id INTO quiz FROM quiz_questions WHERE id=NEW.question_id;
  IF quiz IS NOT NULL THEN PERFORM touch_quiz_index(quiz,0); END IF;
 END IF;
 RETURN NULL;
END;
$$ LANGUAGE plpgsql;
DO $$ BEGIN
 LOCK TABLE quiz_questions,quiz_answer_options IN SHARE ROW EXCLUSIVE MODE;
 INSERT INTO quiz_index_versions(quiz_id,question_count)
SELECT q.id,COUNT(qq.id) FROM quizzes q LEFT JOIN quiz_questions qq ON qq.quiz_id=q.id
GROUP BY q.id ON CONFLICT(quiz_id) DO NOTHING;
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='quiz_question_index_version' AND tgrelid='quiz_questions'::regclass) THEN
  CREATE TRIGGER quiz_question_index_version AFTER INSERT OR UPDATE OR DELETE ON quiz_questions
  FOR EACH ROW EXECUTE FUNCTION track_quiz_question_index();
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='quiz_option_index_version' AND tgrelid='quiz_answer_options'::regclass) THEN
  CREATE TRIGGER quiz_option_index_version AFTER INSERT OR UPDATE OR DELETE ON quiz_answer_options
  FOR EACH ROW EXECUTE FUNCTION track_quiz_option_index();
 END IF;
END $$;
