-- Applies to learning-resource booleans, not courses.status or authoring approval.
-- DEFAULT alone cannot override an explicit false/NULL from an API or MCP client.
CREATE OR REPLACE FUNCTION enforce_learning_publication() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.is_published := true;
    RETURN NEW;
END $$;

ALTER TABLE course_sections ALTER COLUMN is_published SET DEFAULT true;
ALTER TABLE section_content ALTER COLUMN is_published SET DEFAULT true;
ALTER TABLE quizzes ALTER COLUMN is_published SET DEFAULT true;

DROP TRIGGER IF EXISTS enforce_learning_publication ON course_sections;
CREATE TRIGGER enforce_learning_publication BEFORE INSERT OR UPDATE ON course_sections
    FOR EACH ROW EXECUTE FUNCTION enforce_learning_publication();
DROP TRIGGER IF EXISTS enforce_learning_publication ON section_content;
CREATE TRIGGER enforce_learning_publication BEFORE INSERT OR UPDATE ON section_content
    FOR EACH ROW EXECUTE FUNCTION enforce_learning_publication();
DROP TRIGGER IF EXISTS enforce_learning_publication ON quizzes;
CREATE TRIGGER enforce_learning_publication BEFORE INSERT OR UPDATE ON quizzes
    FOR EACH ROW EXECUTE FUNCTION enforce_learning_publication();

-- Quiz writes do not necessarily update section_content. Reuse the existing
-- content-event contract and its per-chapter grouping; no recipient fan-out.
CREATE OR REPLACE FUNCTION capture_quiz_learning_notification() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    sid BIGINT; cid BIGINT; kind TEXT; grouping TEXT;
BEGIN
    SELECT sc.section_id, s.course_id INTO sid, cid
    FROM section_content sc
    JOIN course_sections s ON s.id=sc.section_id AND s.is_published
    JOIN courses c ON c.id=s.course_id AND c.status='PUBLISHED'
    WHERE sc.id=NEW.content_id AND sc.is_published;
    IF cid IS NULL THEN RETURN NULL; END IF;

    IF TG_OP='INSERT' THEN kind := 'content_added';
    ELSIF NOT COALESCE(OLD.is_published, false) THEN kind := 'content_added';
    ELSIF ROW(NEW.title,NEW.description,NEW.instructions,NEW.available_from,NEW.available_until,NEW.time_limit_minutes,NEW.max_attempts)
       IS DISTINCT FROM ROW(OLD.title,OLD.description,OLD.instructions,OLD.available_from,OLD.available_until,OLD.time_limit_minutes,OLD.max_attempts) THEN
        kind := 'content_updated';
    ELSE RETURN NULL; END IF;

    IF kind='content_added' THEN
        grouping := kind || ':' || sid || ':' || floor(extract(epoch FROM now()) / 600)::BIGINT;
    ELSE grouping := kind || ':' || NEW.content_id; END IF;
    INSERT INTO learning_notification_events(course_id,section_id,content_id,kind,entity_title,group_key)
    VALUES(cid,sid,NEW.content_id,kind,NEW.title,grouping);
    RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS capture_quiz_learning_notification ON quizzes;
CREATE TRIGGER capture_quiz_learning_notification AFTER INSERT OR UPDATE ON quizzes
    FOR EACH ROW EXECUTE FUNCTION capture_quiz_learning_notification();

-- Parent first: existing notification triggers can capture newly visible items.
UPDATE course_sections SET is_published=true WHERE is_published IS DISTINCT FROM true;
UPDATE section_content SET is_published=true WHERE is_published IS DISTINCT FROM true;
UPDATE quizzes SET is_published=true WHERE is_published IS DISTINCT FROM true;

ALTER TABLE course_sections ALTER COLUMN is_published SET NOT NULL;
ALTER TABLE section_content ALTER COLUMN is_published SET NOT NULL;
ALTER TABLE quizzes ALTER COLUMN is_published SET NOT NULL;
