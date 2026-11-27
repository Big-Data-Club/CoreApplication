-- Consolidated schema reconstructed from repository SQL, not a Neon dump.
-- NEW databases only. Existing deployments continue using migration history.
-- Tables contain their final columns; indexes, constraints and seed defaults follow.
-- See README.md for scope and regeneration.

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE FUNCTION public.auto_accept_enrollment() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.status      := 'ACCEPTED';
    NEW.accepted_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;



CREATE FUNCTION public.calculate_attempt_score(p_attempt_id bigint) RETURNS void
    LANGUAGE plpgsql
    AS $$
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
$$;



CREATE FUNCTION public.capture_learning_notification() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    row_data JSONB; old_data JSONB;
    cid BIGINT; sid BIGINT; item_id BIGINT; event_kind TEXT; grouping TEXT;
    entity_name TEXT; parent_published BOOLEAN;
BEGIN
    IF TG_OP = 'DELETE' THEN row_data := to_jsonb(OLD); ELSE row_data := to_jsonb(NEW); END IF;
    IF TG_OP = 'UPDATE' THEN old_data := to_jsonb(OLD); END IF;
    entity_name := row_data->>'title';
    IF TG_TABLE_NAME = 'courses' THEN
        IF TG_OP = 'DELETE' OR row_data->>'status' <> 'PUBLISHED' THEN RETURN NULL; END IF;
        cid := (row_data->>'id')::BIGINT;
        IF TG_OP = 'INSERT' OR old_data->>'status' = 'DRAFT' THEN event_kind := 'course_published';
        ELSIF old_data->>'status' IS DISTINCT FROM row_data->>'status'
           OR (row_data - ARRAY['updated_at','published_at','status']) IS DISTINCT FROM (old_data - ARRAY['updated_at','published_at','status']) THEN
            event_kind := 'course_updated';
        ELSE RETURN NULL; END IF;
    ELSIF TG_TABLE_NAME = 'course_sections' THEN
        cid := (row_data->>'course_id')::BIGINT; sid := (row_data->>'id')::BIGINT;
        SELECT status = 'PUBLISHED' INTO parent_published FROM courses WHERE id = cid;
        IF NOT COALESCE(parent_published, false) THEN RETURN NULL; END IF;
        IF TG_OP = 'DELETE' OR NOT (row_data->>'is_published')::BOOLEAN THEN
            IF TG_OP = 'DELETE' AND (row_data->>'is_published')::BOOLEAN
               OR TG_OP = 'UPDATE' AND (old_data->>'is_published')::BOOLEAN THEN event_kind := 'section_removed';
            ELSE RETURN NULL; END IF;
        ELSIF TG_OP = 'INSERT' OR NOT COALESCE((old_data->>'is_published')::BOOLEAN, false) THEN event_kind := 'section_added';
        ELSIF (row_data - 'updated_at') IS DISTINCT FROM (old_data - 'updated_at') THEN event_kind := 'section_updated';
        ELSE RETURN NULL; END IF;
    ELSE
        sid := (row_data->>'section_id')::BIGINT; item_id := (row_data->>'id')::BIGINT;
        SELECT s.course_id, s.is_published AND c.status = 'PUBLISHED' INTO cid, parent_published
            FROM course_sections s JOIN courses c ON c.id = s.course_id WHERE s.id = sid;
        IF NOT COALESCE(parent_published, false) THEN RETURN NULL; END IF;
        IF TG_OP = 'DELETE' OR NOT (row_data->>'is_published')::BOOLEAN THEN
            IF TG_OP = 'DELETE' AND (row_data->>'is_published')::BOOLEAN
               OR TG_OP = 'UPDATE' AND (old_data->>'is_published')::BOOLEAN THEN event_kind := 'content_removed';
            ELSE RETURN NULL; END IF;
        ELSIF TG_OP = 'INSERT' OR NOT COALESCE((old_data->>'is_published')::BOOLEAN, false) THEN event_kind := 'content_added';
        ELSIF ROW(row_data->'section_id', row_data->'title', row_data->'description', row_data->'metadata', row_data->'file_path', row_data->'order_index', row_data->'is_mandatory')
            IS DISTINCT FROM ROW(old_data->'section_id', old_data->'title', old_data->'description', old_data->'metadata', old_data->'file_path', old_data->'order_index', old_data->'is_mandatory') THEN event_kind := 'content_updated';
        ELSE RETURN NULL; END IF;
    END IF;
    -- Bulk uploads form one section notification per ten-minute window.
    IF event_kind = 'content_added' THEN
        grouping := event_kind || ':' || sid || ':' || floor(extract(epoch FROM now()) / 600)::BIGINT;
    ELSE
        grouping := event_kind || ':' || COALESCE(item_id, sid, cid);
    END IF;
    INSERT INTO learning_notification_events(course_id, section_id, content_id, kind, entity_title, group_key)
        VALUES (cid, sid, item_id, event_kind, entity_name, grouping);
    RETURN NULL;
END $$;



CREATE FUNCTION public.capture_quiz_assessment_snapshot() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    SELECT node_id,points INTO NEW.assessed_node_id,NEW.assessed_max_points
    FROM quiz_questions WHERE id=NEW.question_id;
    NEW.assessment_snapshot_origin := 'at_answer';
    RETURN NEW;
END;
$$;



CREATE FUNCTION public.capture_quiz_learning_notification() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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



CREATE FUNCTION public.count_question_blanks(question_text text) RETURNS integer
    LANGUAGE plpgsql IMMUTABLE
    AS $$
DECLARE blank_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO blank_count
    FROM regexp_matches(question_text, '\{BLANK_\d+\}', 'g');
    RETURN COALESCE(blank_count, 0);
END;
$$;



CREATE FUNCTION public.enforce_learning_publication() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.is_published := true;
    RETURN NEW;
END $$;



CREATE FUNCTION public.lms_notification_scope(viewer bigint) RETURNS TABLE(course_id bigint, title character varying, org_id bigint, visibility character varying, enrolled boolean)
    LANGUAGE sql STABLE
    AS $$
    SELECT c.id, c.title, c.org_id, c.visibility,
        EXISTS (SELECT 1 FROM enrollments e WHERE e.student_id = viewer AND e.course_id = c.id AND e.status = 'ACCEPTED')
    FROM courses c WHERE c.status = 'PUBLISHED' AND (
        EXISTS (SELECT 1 FROM organization_members m WHERE m.user_id = viewer AND m.org_id = c.org_id)
        OR (c.visibility = 'PUBLIC' AND NOT EXISTS (
            SELECT 1 FROM organization_members m JOIN organizations o ON o.id = m.org_id
            WHERE m.user_id = viewer AND COALESCE(o.settings->>'allow_cross_org_courses', 'false') <> 'true'
        ))
    )
$$;



CREATE FUNCTION public.reset_ai_index_timestamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
$$;



CREATE FUNCTION public.touch_quiz_index(quiz bigint, delta integer) RETURNS void
    LANGUAGE sql
    AS $$
 INSERT INTO quiz_index_versions(quiz_id,question_count)
 SELECT id,GREATEST(0,delta) FROM quizzes WHERE id=quiz
 ON CONFLICT(quiz_id) DO UPDATE SET revision=quiz_index_versions.revision+1,
 question_count=GREATEST(0,quiz_index_versions.question_count+delta);
$$;



CREATE FUNCTION public.track_quiz_option_index() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
$$;



CREATE FUNCTION public.track_quiz_question_index() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
$$;



CREATE FUNCTION public.update_post_comment_count() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE forum_posts SET comment_count = comment_count + 1 WHERE id = NEW.post_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE forum_posts SET comment_count = comment_count - 1 WHERE id = OLD.post_id;
    END IF;
    RETURN NULL;
END;
$$;



CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;



CREATE FUNCTION public.update_vote_counts() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;


CREATE TABLE public.bulk_enrollment_logs (
    id bigint NOT NULL,
    course_id bigint NOT NULL,
    teacher_id bigint NOT NULL,
    total_count integer NOT NULL,
    success_count integer DEFAULT 0,
    failed_count integer DEFAULT 0,
    status character varying(20) DEFAULT 'PROCESSING'::character varying,
    error_message text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamp without time zone
);



CREATE SEQUENCE public.bulk_enrollment_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.bulk_enrollment_logs_id_seq OWNED BY public.bulk_enrollment_logs.id;



CREATE TABLE public.competency_frameworks (
    id bigint NOT NULL,
    organization_id bigint,
    code character varying(100) NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    subject character varying(100),
    locale character varying(20) DEFAULT 'und'::character varying NOT NULL,
    version character varying(50) DEFAULT '1.0'::character varying NOT NULL,
    status character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by bigint,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT competency_frameworks_status_check CHECK (((status)::text = ANY (ARRAY[('DRAFT'::character varying)::text, ('PUBLISHED'::character varying)::text, ('ARCHIVED'::character varying)::text])))
);



CREATE SEQUENCE public.competency_frameworks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.competency_frameworks_id_seq OWNED BY public.competency_frameworks.id;



CREATE TABLE public.content_progress (
    id bigint NOT NULL,
    content_id bigint NOT NULL,
    student_id bigint NOT NULL,
    completed_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.content_progress_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.content_progress_id_seq OWNED BY public.content_progress.id;



CREATE TABLE public.content_skills (
    id bigint NOT NULL,
    content_id bigint NOT NULL,
    skill_id bigint NOT NULL,
    difficulty double precision,
    weight double precision DEFAULT 1.0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT content_skills_difficulty_check CHECK (((difficulty >= (0)::double precision) AND (difficulty <= (1)::double precision))),
    CONSTRAINT content_skills_weight_check CHECK (((weight >= (0)::double precision) AND (weight <= (1)::double precision)))
);



CREATE SEQUENCE public.content_skills_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.content_skills_id_seq OWNED BY public.content_skills.id;



CREATE TABLE public.course_co_teachers (
    id bigint NOT NULL,
    course_id bigint NOT NULL,
    user_id bigint NOT NULL,
    added_by bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.course_co_teachers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.course_co_teachers_id_seq OWNED BY public.course_co_teachers.id;



CREATE TABLE public.course_competencies (
    id bigint NOT NULL,
    course_id bigint NOT NULL,
    skill_id bigint NOT NULL,
    target_mastery double precision DEFAULT 0.8 NOT NULL,
    weight double precision DEFAULT 1.0 NOT NULL,
    is_required boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT course_competencies_target_mastery_check CHECK (((target_mastery >= (0)::double precision) AND (target_mastery <= (1)::double precision))),
    CONSTRAINT course_competencies_weight_check CHECK (((weight >= (0)::double precision) AND (weight <= (1)::double precision)))
);



CREATE SEQUENCE public.course_competencies_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.course_competencies_id_seq OWNED BY public.course_competencies.id;



CREATE TABLE public.course_sections (
    id bigint NOT NULL,
    course_id bigint NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    order_index integer NOT NULL,
    is_published boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.course_sections_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.course_sections_id_seq OWNED BY public.course_sections.id;



CREATE TABLE public.courses (
    id bigint NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    category character varying(100),
    level character varying(50),
    thumbnail_url character varying(500),
    status character varying(50) DEFAULT 'DRAFT'::character varying,
    created_by bigint NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    published_at timestamp without time zone,
    org_id bigint NOT NULL,
    visibility character varying(20) DEFAULT 'PUBLIC'::character varying,
    archived_from_status character varying(50),
    CONSTRAINT courses_archived_from_status_check CHECK (((archived_from_status IS NULL) OR ((archived_from_status)::text = ANY (ARRAY[('DRAFT'::character varying)::text, ('PUBLISHED'::character varying)::text])))),
    CONSTRAINT courses_level_check CHECK (((level)::text = ANY (ARRAY[('BEGINNER'::character varying)::text, ('INTERMEDIATE'::character varying)::text, ('ADVANCED'::character varying)::text, ('ALL_LEVELS'::character varying)::text]))),
    CONSTRAINT courses_status_check CHECK (((status)::text = ANY (ARRAY[('DRAFT'::character varying)::text, ('PUBLISHED'::character varying)::text, ('ARCHIVED'::character varying)::text]))),
    CONSTRAINT courses_visibility_check CHECK (((visibility)::text = ANY (ARRAY[('PUBLIC'::character varying)::text, ('ORG_ONLY'::character varying)::text])))
);



CREATE SEQUENCE public.courses_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.courses_id_seq OWNED BY public.courses.id;



CREATE TABLE public.enrollments (
    id bigint NOT NULL,
    course_id bigint NOT NULL,
    student_id bigint NOT NULL,
    status character varying(20) DEFAULT 'ACCEPTED'::character varying NOT NULL,
    enrolled_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    accepted_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    rejected_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.enrollments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.enrollments_id_seq OWNED BY public.enrollments.id;



CREATE TABLE public.farm_learning_attempts (
    challenge_id uuid NOT NULL,
    user_id bigint NOT NULL,
    course_id bigint NOT NULL,
    node_id bigint,
    source_id text NOT NULL,
    kind text NOT NULL,
    correct boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT farm_learning_attempts_kind_check CHECK ((kind = ANY (ARRAY['quiz'::text, 'flashcard'::text])))
);



CREATE TABLE public.forum_comments (
    id bigint NOT NULL,
    post_id bigint NOT NULL,
    parent_comment_id bigint,
    user_id bigint NOT NULL,
    body text NOT NULL,
    upvotes integer DEFAULT 0,
    downvotes integer DEFAULT 0,
    is_accepted boolean DEFAULT false,
    depth integer DEFAULT 0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.forum_comments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.forum_comments_id_seq OWNED BY public.forum_comments.id;



CREATE TABLE public.forum_posts (
    id bigint NOT NULL,
    content_id bigint NOT NULL,
    user_id bigint NOT NULL,
    title character varying(255) NOT NULL,
    body text NOT NULL,
    tags character varying(100)[] DEFAULT '{}'::character varying[],
    upvotes integer DEFAULT 0,
    downvotes integer DEFAULT 0,
    comment_count integer DEFAULT 0,
    view_count integer DEFAULT 0,
    is_pinned boolean DEFAULT false,
    is_locked boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.forum_posts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.forum_posts_id_seq OWNED BY public.forum_posts.id;



CREATE TABLE public.forum_votes (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    votable_type character varying(20) NOT NULL,
    votable_id bigint NOT NULL,
    vote_type character varying(10) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT forum_votes_votable_type_check CHECK (((votable_type)::text = ANY (ARRAY[('post'::character varying)::text, ('comment'::character varying)::text]))),
    CONSTRAINT forum_votes_vote_type_check CHECK (((vote_type)::text = ANY (ARRAY[('upvote'::character varying)::text, ('downvote'::character varying)::text])))
);



CREATE SEQUENCE public.forum_votes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.forum_votes_id_seq OWNED BY public.forum_votes.id;



CREATE TABLE public.knowledge_node_mastery (
    user_id bigint NOT NULL,
    course_id bigint NOT NULL,
    node_id bigint NOT NULL,
    formal_quiz_score double precision DEFAULT 0 NOT NULL,
    formal_quiz_count integer DEFAULT 0 NOT NULL,
    mini_quiz_score double precision DEFAULT 0 NOT NULL,
    mini_quiz_count integer DEFAULT 0 NOT NULL,
    completion_score double precision DEFAULT 0 NOT NULL,
    completion_count integer DEFAULT 0 NOT NULL,
    engagement_score double precision DEFAULT 0 NOT NULL,
    engagement_count integer DEFAULT 0 NOT NULL,
    mastery_level double precision DEFAULT 0 NOT NULL,
    last_interaction_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);



CREATE TABLE public.learner_skill_states (
    id bigint NOT NULL,
    student_id bigint NOT NULL,
    skill_id bigint NOT NULL,
    mastery_score double precision DEFAULT 0.0,
    confidence_score double precision DEFAULT 0.0,
    attempt_count integer DEFAULT 0,
    accuracy double precision DEFAULT 0.0,
    avg_response_time_ms bigint,
    hint_dependency double precision DEFAULT 0.0,
    last_practiced_at timestamp without time zone,
    recommended_difficulty double precision,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT learner_skill_states_accuracy_check CHECK (((accuracy >= (0)::double precision) AND (accuracy <= (1)::double precision))),
    CONSTRAINT learner_skill_states_confidence_score_check CHECK (((confidence_score >= (0)::double precision) AND (confidence_score <= (1)::double precision))),
    CONSTRAINT learner_skill_states_hint_dependency_check CHECK (((hint_dependency >= (0)::double precision) AND (hint_dependency <= (1)::double precision))),
    CONSTRAINT learner_skill_states_mastery_score_check CHECK (((mastery_score >= (0)::double precision) AND (mastery_score <= (1)::double precision))),
    CONSTRAINT learner_skill_states_recommended_difficulty_check CHECK (((recommended_difficulty >= (0)::double precision) AND (recommended_difficulty <= (1)::double precision)))
);



CREATE SEQUENCE public.learner_skill_states_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.learner_skill_states_id_seq OWNED BY public.learner_skill_states.id;



CREATE TABLE public.learning_events (
    id bigint NOT NULL,
    event_id character varying(100) NOT NULL,
    event_type character varying(50) NOT NULL,
    student_id bigint NOT NULL,
    session_id character varying(100),
    course_id bigint,
    lesson_id bigint,
    question_id bigint,
    skill_id bigint,
    difficulty double precision,
    correct boolean,
    attempt_no integer,
    response_time_ms bigint,
    hint_count integer,
    metadata jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT learning_events_difficulty_check CHECK (((difficulty >= (0)::double precision) AND (difficulty <= (1)::double precision))),
    CONSTRAINT learning_events_event_type_check CHECK (((event_type)::text = ANY (ARRAY[('lesson_opened'::character varying)::text, ('lesson_started'::character varying)::text, ('lesson_completed'::character varying)::text, ('lesson_abandoned'::character varying)::text, ('lesson_resumed'::character varying)::text, ('question_viewed'::character varying)::text, ('answer_submitted'::character varying)::text, ('answer_retried'::character varying)::text, ('hint_requested'::character varying)::text, ('recommendation_clicked'::character varying)::text])))
);



CREATE SEQUENCE public.learning_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.learning_events_id_seq OWNED BY public.learning_events.id;



CREATE TABLE public.learning_notification_events (
    id bigint NOT NULL,
    course_id bigint NOT NULL,
    section_id bigint,
    content_id bigint,
    kind text NOT NULL,
    entity_title text NOT NULL,
    group_key text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    delivered_at timestamp with time zone
);



CREATE SEQUENCE public.learning_notification_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.learning_notification_events_id_seq OWNED BY public.learning_notification_events.id;



CREATE TABLE public.learning_notification_reads (
    user_id bigint NOT NULL,
    notification_key character varying(160) NOT NULL,
    read_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.lms_callback_receipts (
    kind text NOT NULL,
    job_id bigint NOT NULL,
    payload_hash text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.lms_file_assets (
    file_path text NOT NULL,
    owner_user_id bigint NOT NULL,
    size_bytes bigint NOT NULL,
    visibility text DEFAULT 'private'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT lms_file_assets_owner_user_id_check CHECK ((owner_user_id > 0)),
    CONSTRAINT lms_file_assets_size_bytes_check CHECK ((size_bytes >= 0)),
    CONSTRAINT lms_file_assets_visibility_check CHECK ((visibility = ANY (ARRAY['private'::text, 'public'::text])))
);



CREATE TABLE public.lms_processed_interactions (
    interaction_id bigint NOT NULL,
    processed_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE TABLE public.lms_quiz_effects (
    attempt_id bigint NOT NULL,
    available_at timestamp with time zone DEFAULT now() NOT NULL,
    local_completed_at timestamp with time zone,
    completed_at timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    last_error text DEFAULT ''::text NOT NULL
);



CREATE TABLE public.micro_lesson_interactions (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    course_id bigint NOT NULL,
    lesson_id bigint,
    node_id bigint,
    action_type character varying(40) NOT NULL,
    score double precision,
    status character varying(40),
    payload jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT micro_lesson_interactions_action_type_check CHECK (((action_type)::text = ANY (ARRAY[('lesson_view'::character varying)::text, ('lesson_complete'::character varying)::text, ('flashcard_flip'::character varying)::text, ('flashcard_rate'::character varying)::text, ('quick_check_attempt'::character varying)::text, ('quick_check_correct'::character varying)::text, ('quick_check_incorrect'::character varying)::text, ('ask_ai'::character varying)::text])))
);



CREATE SEQUENCE public.micro_lesson_interactions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.micro_lesson_interactions_id_seq OWNED BY public.micro_lesson_interactions.id;



CREATE TABLE public.micro_lesson_jobs (
    id bigint NOT NULL,
    course_id bigint NOT NULL,
    section_id bigint,
    source_content_id bigint,
    source_file_path character varying(1000),
    source_file_type character varying(100),
    source_url character varying(1000),
    target_minutes integer DEFAULT 5 NOT NULL,
    language character varying(10) DEFAULT 'vi'::character varying NOT NULL,
    status character varying(20) DEFAULT 'queued'::character varying NOT NULL,
    progress integer DEFAULT 0,
    stage character varying(64) DEFAULT ''::character varying,
    lessons_count integer DEFAULT 0,
    error text,
    created_by bigint NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamp without time zone,
    CONSTRAINT micro_lesson_jobs_status_check CHECK (((status)::text = ANY (ARRAY[('queued'::character varying)::text, ('processing'::character varying)::text, ('completed'::character varying)::text, ('failed'::character varying)::text])))
);



CREATE SEQUENCE public.micro_lesson_jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.micro_lesson_jobs_id_seq OWNED BY public.micro_lesson_jobs.id;



CREATE TABLE public.micro_lessons (
    id bigint NOT NULL,
    job_id bigint NOT NULL,
    course_id bigint NOT NULL,
    section_id bigint,
    source_content_id bigint,
    title character varying(500) NOT NULL,
    summary text,
    objectives jsonb DEFAULT '[]'::jsonb,
    markdown_content text NOT NULL,
    estimated_minutes integer DEFAULT 5,
    order_index integer DEFAULT 0 NOT NULL,
    status character varying(20) DEFAULT 'draft'::character varying NOT NULL,
    published_content_id bigint,
    image_urls jsonb DEFAULT '[]'::jsonb,
    language character varying(10) DEFAULT 'vi'::character varying,
    node_id bigint,
    created_by bigint NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    published_at timestamp without time zone,
    CONSTRAINT micro_lessons_status_check CHECK (((status)::text = ANY (ARRAY[('draft'::character varying)::text, ('published'::character varying)::text, ('archived'::character varying)::text])))
);



CREATE SEQUENCE public.micro_lessons_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.micro_lessons_id_seq OWNED BY public.micro_lessons.id;



CREATE TABLE public.micro_quiz_jobs (
    id bigint NOT NULL,
    course_id bigint NOT NULL,
    section_id bigint,
    source_content_id bigint,
    source_file_path character varying(1000),
    source_file_type character varying(100),
    source_url character varying(1000),
    language character varying(10) DEFAULT 'vi'::character varying NOT NULL,
    status character varying(20) DEFAULT 'queued'::character varying NOT NULL,
    progress integer DEFAULT 0,
    stage character varying(64) DEFAULT ''::character varying,
    quizzes_count integer DEFAULT 0,
    error text,
    created_by bigint NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamp without time zone,
    CONSTRAINT micro_quiz_jobs_status_check CHECK (((status)::text = ANY (ARRAY[('queued'::character varying)::text, ('processing'::character varying)::text, ('completed'::character varying)::text, ('failed'::character varying)::text])))
);



CREATE SEQUENCE public.micro_quiz_jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.micro_quiz_jobs_id_seq OWNED BY public.micro_quiz_jobs.id;



CREATE TABLE public.micro_quizzes (
    id bigint NOT NULL,
    job_id bigint NOT NULL,
    course_id bigint NOT NULL,
    section_id bigint,
    source_content_id bigint,
    title character varying(500) NOT NULL,
    summary text,
    questions_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    questions_count integer DEFAULT 0,
    order_index integer DEFAULT 0 NOT NULL,
    status character varying(20) DEFAULT 'draft'::character varying NOT NULL,
    published_content_id bigint,
    node_id bigint,
    language character varying(10) DEFAULT 'vi'::character varying,
    created_by bigint NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    published_at timestamp without time zone,
    CONSTRAINT micro_quizzes_status_check CHECK (((status)::text = ANY (ARRAY[('draft'::character varying)::text, ('published'::character varying)::text, ('archived'::character varying)::text])))
);



CREATE SEQUENCE public.micro_quizzes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.micro_quizzes_id_seq OWNED BY public.micro_quizzes.id;



CREATE TABLE public.organization_members (
    id bigint NOT NULL,
    org_id bigint NOT NULL,
    user_id bigint NOT NULL,
    org_role character varying(20) DEFAULT 'MEMBER'::character varying NOT NULL,
    joined_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT organization_members_org_role_check CHECK (((org_role)::text = ANY (ARRAY[('OWNER'::character varying)::text, ('ADMIN'::character varying)::text, ('MEMBER'::character varying)::text])))
);



CREATE SEQUENCE public.organization_members_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.organization_members_id_seq OWNED BY public.organization_members.id;



CREATE TABLE public.organizations (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    slug character varying(100) NOT NULL,
    description text,
    logo_url character varying(500),
    is_active boolean DEFAULT true NOT NULL,
    settings jsonb DEFAULT '{"allow_cross_org_courses": true, "default_course_visibility": "PUBLIC"}'::jsonb NOT NULL,
    created_by bigint,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.organizations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.organizations_id_seq OWNED BY public.organizations.id;



CREATE TABLE public.permissions (
    id bigint NOT NULL,
    code character varying(80) NOT NULL,
    module character varying(40) NOT NULL,
    description character varying(255),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.permissions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.permissions_id_seq OWNED BY public.permissions.id;



CREATE TABLE public.question_bank_items (
    id bigint NOT NULL,
    course_id bigint NOT NULL,
    node_id bigint,
    source_quiz_id bigint,
    question_type character varying(50) NOT NULL,
    question_text text NOT NULL,
    explanation text,
    points numeric(10,2) DEFAULT 10.00 NOT NULL,
    bloom_level character varying(20),
    difficulty character varying(20) DEFAULT 'MEDIUM'::character varying NOT NULL,
    answer_options jsonb DEFAULT '[]'::jsonb NOT NULL,
    correct_answers jsonb DEFAULT '[]'::jsonb NOT NULL,
    settings jsonb DEFAULT '{}'::jsonb NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    source character varying(20) DEFAULT 'MANUAL'::character varying NOT NULL,
    status character varying(20) DEFAULT 'APPROVED'::character varying NOT NULL,
    created_by bigint NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT question_bank_items_bloom_level_check CHECK (((bloom_level)::text = ANY (ARRAY[('remember'::character varying)::text, ('understand'::character varying)::text, ('apply'::character varying)::text, ('analyze'::character varying)::text, ('evaluate'::character varying)::text, ('create'::character varying)::text]))),
    CONSTRAINT question_bank_items_difficulty_check CHECK (((difficulty)::text = ANY (ARRAY[('EASY'::character varying)::text, ('MEDIUM'::character varying)::text, ('HARD'::character varying)::text]))),
    CONSTRAINT question_bank_items_points_check CHECK ((points >= (0)::numeric)),
    CONSTRAINT question_bank_items_question_type_check CHECK (((question_type)::text = ANY (ARRAY[('SINGLE_CHOICE'::character varying)::text, ('MULTIPLE_CHOICE'::character varying)::text, ('SHORT_ANSWER'::character varying)::text, ('ESSAY'::character varying)::text, ('FILE_UPLOAD'::character varying)::text, ('FILL_BLANK_TEXT'::character varying)::text, ('FILL_BLANK_DROPDOWN'::character varying)::text]))),
    CONSTRAINT question_bank_items_source_check CHECK (((source)::text = ANY (ARRAY[('MANUAL'::character varying)::text, ('IMPORT'::character varying)::text, ('AI_GENERATED'::character varying)::text, ('QUIZ'::character varying)::text]))),
    CONSTRAINT question_bank_items_status_check CHECK (((status)::text = ANY (ARRAY[('DRAFT'::character varying)::text, ('APPROVED'::character varying)::text, ('DISABLED'::character varying)::text])))
);



CREATE SEQUENCE public.question_bank_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.question_bank_items_id_seq OWNED BY public.question_bank_items.id;



CREATE TABLE public.question_skills (
    id bigint NOT NULL,
    question_id bigint NOT NULL,
    skill_id bigint NOT NULL,
    difficulty double precision,
    weight double precision DEFAULT 1.0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT question_skills_difficulty_check CHECK (((difficulty >= (0)::double precision) AND (difficulty <= (1)::double precision))),
    CONSTRAINT question_skills_weight_check CHECK (((weight >= (0)::double precision) AND (weight <= (1)::double precision)))
);



CREATE SEQUENCE public.question_skills_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.question_skills_id_seq OWNED BY public.question_skills.id;



CREATE TABLE public.quiz_analytics (
    id bigint NOT NULL,
    quiz_id bigint NOT NULL,
    question_id bigint,
    total_attempts integer DEFAULT 0,
    correct_count integer DEFAULT 0,
    incorrect_count integer DEFAULT 0,
    average_score numeric(5,2),
    difficulty_rating character varying(20),
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.quiz_analytics_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.quiz_analytics_id_seq OWNED BY public.quiz_analytics.id;



CREATE TABLE public.quiz_answer_options (
    id bigint NOT NULL,
    question_id bigint NOT NULL,
    option_text text NOT NULL,
    option_html text,
    is_correct boolean DEFAULT false,
    order_index integer NOT NULL,
    blank_id integer,
    settings jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.quiz_answer_options_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.quiz_answer_options_id_seq OWNED BY public.quiz_answer_options.id;



CREATE TABLE public.quiz_attempts (
    id bigint NOT NULL,
    quiz_id bigint NOT NULL,
    student_id bigint NOT NULL,
    attempt_number integer DEFAULT 1 NOT NULL,
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    submitted_at timestamp without time zone,
    time_spent_seconds integer,
    total_points numeric(10,2),
    earned_points numeric(10,2),
    percentage numeric(5,2),
    is_passed boolean,
    status character varying(20) DEFAULT 'IN_PROGRESS'::character varying,
    auto_graded_at timestamp without time zone,
    manually_graded_at timestamp without time zone,
    graded_by bigint,
    ip_address character varying(45),
    user_agent text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    focus_summary jsonb,
    CONSTRAINT quiz_attempts_status_check CHECK (((status)::text = ANY (ARRAY[('IN_PROGRESS'::character varying)::text, ('SUBMITTED'::character varying)::text, ('GRADED'::character varying)::text, ('ABANDONED'::character varying)::text])))
);



CREATE SEQUENCE public.quiz_attempts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.quiz_attempts_id_seq OWNED BY public.quiz_attempts.id;



CREATE TABLE public.quiz_correct_answers (
    id bigint NOT NULL,
    question_id bigint NOT NULL,
    answer_text text,
    blank_id integer,
    blank_position integer,
    case_sensitive boolean DEFAULT false,
    exact_match boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.quiz_correct_answers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.quiz_correct_answers_id_seq OWNED BY public.quiz_correct_answers.id;



CREATE TABLE public.quiz_index_versions (
    quiz_id bigint NOT NULL,
    revision bigint DEFAULT 1 NOT NULL,
    question_count bigint DEFAULT 0 NOT NULL,
    CONSTRAINT quiz_index_versions_question_count_check CHECK ((question_count >= 0))
);



CREATE TABLE public.quiz_questions (
    id bigint NOT NULL,
    quiz_id bigint NOT NULL,
    question_type character varying(50) NOT NULL,
    question_text text NOT NULL,
    question_html text,
    explanation text,
    points numeric(10,2) DEFAULT 10.00,
    order_index integer NOT NULL,
    settings jsonb DEFAULT '{}'::jsonb,
    is_required boolean DEFAULT true,
    node_id bigint,
    bloom_level character varying(20),
    reference_chunk_id bigint,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT quiz_questions_bloom_level_check CHECK (((bloom_level)::text = ANY (ARRAY[('remember'::character varying)::text, ('understand'::character varying)::text, ('apply'::character varying)::text, ('analyze'::character varying)::text, ('evaluate'::character varying)::text, ('create'::character varying)::text]))),
    CONSTRAINT quiz_questions_question_type_check CHECK (((question_type)::text = ANY (ARRAY[('SINGLE_CHOICE'::character varying)::text, ('MULTIPLE_CHOICE'::character varying)::text, ('SHORT_ANSWER'::character varying)::text, ('ESSAY'::character varying)::text, ('FILE_UPLOAD'::character varying)::text, ('FILL_BLANK_TEXT'::character varying)::text, ('FILL_BLANK_DROPDOWN'::character varying)::text])))
);



CREATE SEQUENCE public.quiz_questions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.quiz_questions_id_seq OWNED BY public.quiz_questions.id;



CREATE TABLE public.quiz_student_answers (
    id bigint NOT NULL,
    attempt_id bigint NOT NULL,
    question_id bigint NOT NULL,
    answer_data jsonb NOT NULL,
    points_earned numeric(10,2),
    is_correct boolean,
    grader_feedback text,
    graded_by bigint,
    graded_at timestamp without time zone,
    answered_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    time_spent_seconds integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    assessed_node_id bigint,
    assessed_max_points numeric,
    assessment_snapshot_origin text
);



CREATE SEQUENCE public.quiz_student_answers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.quiz_student_answers_id_seq OWNED BY public.quiz_student_answers.id;



CREATE VIEW public.quiz_summary_view AS
SELECT
    NULL::bigint AS id,
    NULL::bigint AS content_id,
    NULL::character varying(500) AS title,
    NULL::text AS description,
    NULL::text AS instructions,
    NULL::integer AS time_limit_minutes,
    NULL::timestamp without time zone AS available_from,
    NULL::timestamp without time zone AS available_until,
    NULL::integer AS max_attempts,
    NULL::boolean AS shuffle_questions,
    NULL::boolean AS shuffle_answers,
    NULL::numeric(5,2) AS passing_score,
    NULL::numeric(10,2) AS total_points,
    NULL::boolean AS auto_grade,
    NULL::boolean AS show_results_immediately,
    NULL::boolean AS show_correct_answers,
    NULL::boolean AS allow_review,
    NULL::boolean AS show_feedback,
    NULL::boolean AS is_published,
    NULL::bigint AS created_by,
    NULL::timestamp without time zone AS created_at,
    NULL::timestamp without time zone AS updated_at,
    NULL::character varying(255) AS creator_name,
    NULL::character varying(255) AS creator_email,
    NULL::bigint AS question_count,
    NULL::bigint AS attempt_count,
    NULL::bigint AS student_count,
    NULL::numeric AS average_score,
    NULL::bigint AS passed_count;



CREATE TABLE public.quizzes (
    id bigint NOT NULL,
    content_id bigint NOT NULL,
    title character varying(500) NOT NULL,
    description text,
    instructions text,
    time_limit_minutes integer,
    available_from timestamp without time zone,
    available_until timestamp without time zone,
    max_attempts integer DEFAULT 1,
    shuffle_questions boolean DEFAULT false,
    shuffle_answers boolean DEFAULT false,
    passing_score numeric(5,2),
    total_points numeric(10,2) DEFAULT 100.00,
    auto_grade boolean DEFAULT true,
    show_results_immediately boolean DEFAULT true,
    show_correct_answers boolean DEFAULT true,
    allow_review boolean DEFAULT true,
    show_feedback boolean DEFAULT true,
    is_published boolean DEFAULT true NOT NULL,
    created_by bigint NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.quizzes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.quizzes_id_seq OWNED BY public.quizzes.id;



CREATE TABLE public.role_definitions (
    id bigint NOT NULL,
    name character varying(50) NOT NULL,
    display_name character varying(100),
    description text,
    is_system boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE SEQUENCE public.role_definitions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.role_definitions_id_seq OWNED BY public.role_definitions.id;



CREATE TABLE public.role_permissions (
    role_id bigint NOT NULL,
    permission_id bigint NOT NULL,
    assigned_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);



CREATE TABLE public.section_content (
    id bigint NOT NULL,
    section_id bigint NOT NULL,
    type character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    order_index integer NOT NULL,
    metadata jsonb,
    is_published boolean DEFAULT true NOT NULL,
    is_mandatory boolean DEFAULT false,
    file_path character varying(1000),
    file_size bigint,
    file_type character varying(100),
    ai_index_status character varying(20) DEFAULT 'not_indexed'::character varying,
    ai_index_job_id bigint,
    ai_indexed_at timestamp without time zone,
    embedding_model character varying(64) DEFAULT 'bge-m3'::character varying,
    created_by bigint NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT section_content_ai_index_status_check CHECK (((ai_index_status)::text = ANY (ARRAY[('not_indexed'::character varying)::text, ('processing'::character varying)::text, ('indexed'::character varying)::text, ('failed'::character varying)::text]))),
    CONSTRAINT section_content_type_check CHECK (((type)::text = ANY (ARRAY[('TEXT'::character varying)::text, ('VIDEO'::character varying)::text, ('DOCUMENT'::character varying)::text, ('IMAGE'::character varying)::text, ('QUIZ'::character varying)::text, ('FORUM'::character varying)::text, ('ANNOUNCEMENT'::character varying)::text])))
);



CREATE SEQUENCE public.section_content_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.section_content_id_seq OWNED BY public.section_content.id;



CREATE TABLE public.section_overview_jobs (
    id bigint NOT NULL,
    section_id bigint NOT NULL,
    course_id bigint NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    progress integer DEFAULT 0 NOT NULL,
    stage text DEFAULT ''::text NOT NULL,
    error_msg text DEFAULT ''::text NOT NULL,
    language text DEFAULT 'vi'::text NOT NULL,
    question_count integer DEFAULT 10 NOT NULL,
    created_by bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    logs text DEFAULT ''::text NOT NULL
);



CREATE SEQUENCE public.section_overview_jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.section_overview_jobs_id_seq OWNED BY public.section_overview_jobs.id;



CREATE TABLE public.section_overview_lessons (
    id bigint NOT NULL,
    job_id bigint NOT NULL,
    section_id bigint NOT NULL,
    course_id bigint NOT NULL,
    title text DEFAULT ''::text NOT NULL,
    summary text DEFAULT ''::text NOT NULL,
    markdown_content text DEFAULT ''::text NOT NULL,
    references_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    published_content_id bigint,
    created_by bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.section_overview_lessons_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.section_overview_lessons_id_seq OWNED BY public.section_overview_lessons.id;



CREATE TABLE public.section_overview_quizzes (
    id bigint NOT NULL,
    job_id bigint NOT NULL,
    section_id bigint NOT NULL,
    course_id bigint NOT NULL,
    title text DEFAULT ''::text NOT NULL,
    summary text DEFAULT ''::text NOT NULL,
    question_count integer DEFAULT 10 NOT NULL,
    questions_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    references_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    published_quiz_id bigint,
    created_by bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);



CREATE SEQUENCE public.section_overview_quizzes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.section_overview_quizzes_id_seq OWNED BY public.section_overview_quizzes.id;



CREATE TABLE public.skill_prerequisites (
    id bigint NOT NULL,
    skill_id bigint NOT NULL,
    prerequisite_skill_id bigint NOT NULL,
    strength double precision DEFAULT 1.0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT skill_prerequisites_check CHECK ((skill_id <> prerequisite_skill_id)),
    CONSTRAINT skill_prerequisites_strength_check CHECK (((strength >= (0)::double precision) AND (strength <= (1)::double precision)))
);



CREATE SEQUENCE public.skill_prerequisites_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.skill_prerequisites_id_seq OWNED BY public.skill_prerequisites.id;



CREATE TABLE public.skill_recommendations (
    id bigint NOT NULL,
    recommendation_id character varying(100) NOT NULL,
    student_id bigint NOT NULL,
    course_id bigint,
    content_id bigint,
    skill_id bigint,
    difficulty double precision,
    reason character varying(255),
    recommendation_score double precision,
    clicked boolean DEFAULT false,
    clicked_at timestamp without time zone,
    completed boolean DEFAULT false,
    completed_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT skill_recommendations_difficulty_check CHECK (((difficulty >= (0)::double precision) AND (difficulty <= (1)::double precision))),
    CONSTRAINT skill_recommendations_recommendation_score_check CHECK (((recommendation_score >= (0)::double precision) AND (recommendation_score <= (1)::double precision)))
);



CREATE SEQUENCE public.skill_recommendations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.skill_recommendations_id_seq OWNED BY public.skill_recommendations.id;



CREATE TABLE public.skill_relationships (
    id bigint NOT NULL,
    source_skill_id bigint NOT NULL,
    target_skill_id bigint NOT NULL,
    relationship_type character varying(30) NOT NULL,
    strength double precision DEFAULT 1.0 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT skill_relationships_check CHECK ((source_skill_id <> target_skill_id)),
    CONSTRAINT skill_relationships_relationship_type_check CHECK (((relationship_type)::text = ANY (ARRAY[('PREREQUISITE'::character varying)::text, ('PART_OF'::character varying)::text, ('RELATED'::character varying)::text, ('EQUIVALENT'::character varying)::text]))),
    CONSTRAINT skill_relationships_strength_check CHECK (((strength >= (0)::double precision) AND (strength <= (1)::double precision)))
);



CREATE SEQUENCE public.skill_relationships_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.skill_relationships_id_seq OWNED BY public.skill_relationships.id;



CREATE TABLE public.skills (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    parent_skill_id bigint,
    difficulty double precision,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    framework_id bigint,
    code character varying(100),
    competency_type character varying(30) DEFAULT 'KNOWLEDGE'::character varying NOT NULL,
    status character varying(20) DEFAULT 'ACTIVE'::character varying NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT skills_competency_type_check CHECK (((competency_type)::text = ANY (ARRAY[('KNOWLEDGE'::character varying)::text, ('SKILL'::character varying)::text, ('ATTITUDE'::character varying)::text, ('OUTCOME'::character varying)::text]))),
    CONSTRAINT skills_difficulty_check CHECK (((difficulty >= (0)::double precision) AND (difficulty <= (1)::double precision))),
    CONSTRAINT skills_status_check CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('ARCHIVED'::character varying)::text])))
);



CREATE SEQUENCE public.skills_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.skills_id_seq OWNED BY public.skills.id;



CREATE TABLE public.user_roles (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    role character varying(50) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    source character varying(10) DEFAULT 'sync'::character varying,
    CONSTRAINT user_roles_source_check CHECK (((source)::text = ANY (ARRAY[('sync'::character varying)::text, ('manual'::character varying)::text])))
);



CREATE SEQUENCE public.user_roles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.user_roles_id_seq OWNED BY public.user_roles.id;



CREATE TABLE public.users (
    id bigint NOT NULL,
    email character varying(255) NOT NULL,
    full_name character varying(255),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    organization character varying(255),
    profile_picture character varying(1000)
);



CREATE SEQUENCE public.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;



CREATE VIEW public.v_content_ai_status AS
 SELECT sc.id AS content_id,
    sc.title,
    sc.type,
    sc.ai_index_status,
    sc.ai_indexed_at,
    sc.embedding_model,
    cs.course_id,
    c.title AS course_title
   FROM ((public.section_content sc
     JOIN public.course_sections cs ON ((cs.id = sc.section_id)))
     JOIN public.courses c ON ((c.id = cs.course_id)))
  WHERE ((sc.type)::text <> ALL (ARRAY[('QUIZ'::character varying)::text, ('FORUM'::character varying)::text, ('ANNOUNCEMENT'::character varying)::text]))
  ORDER BY sc.ai_index_status, sc.updated_at DESC;



ALTER TABLE ONLY public.bulk_enrollment_logs ALTER COLUMN id SET DEFAULT nextval('public.bulk_enrollment_logs_id_seq'::regclass);



ALTER TABLE ONLY public.competency_frameworks ALTER COLUMN id SET DEFAULT nextval('public.competency_frameworks_id_seq'::regclass);



ALTER TABLE ONLY public.content_progress ALTER COLUMN id SET DEFAULT nextval('public.content_progress_id_seq'::regclass);



ALTER TABLE ONLY public.content_skills ALTER COLUMN id SET DEFAULT nextval('public.content_skills_id_seq'::regclass);



ALTER TABLE ONLY public.course_co_teachers ALTER COLUMN id SET DEFAULT nextval('public.course_co_teachers_id_seq'::regclass);



ALTER TABLE ONLY public.course_competencies ALTER COLUMN id SET DEFAULT nextval('public.course_competencies_id_seq'::regclass);



ALTER TABLE ONLY public.course_sections ALTER COLUMN id SET DEFAULT nextval('public.course_sections_id_seq'::regclass);



ALTER TABLE ONLY public.courses ALTER COLUMN id SET DEFAULT nextval('public.courses_id_seq'::regclass);



ALTER TABLE ONLY public.enrollments ALTER COLUMN id SET DEFAULT nextval('public.enrollments_id_seq'::regclass);



ALTER TABLE ONLY public.forum_comments ALTER COLUMN id SET DEFAULT nextval('public.forum_comments_id_seq'::regclass);



ALTER TABLE ONLY public.forum_posts ALTER COLUMN id SET DEFAULT nextval('public.forum_posts_id_seq'::regclass);



ALTER TABLE ONLY public.forum_votes ALTER COLUMN id SET DEFAULT nextval('public.forum_votes_id_seq'::regclass);



ALTER TABLE ONLY public.learner_skill_states ALTER COLUMN id SET DEFAULT nextval('public.learner_skill_states_id_seq'::regclass);



ALTER TABLE ONLY public.learning_events ALTER COLUMN id SET DEFAULT nextval('public.learning_events_id_seq'::regclass);



ALTER TABLE ONLY public.learning_notification_events ALTER COLUMN id SET DEFAULT nextval('public.learning_notification_events_id_seq'::regclass);



ALTER TABLE ONLY public.micro_lesson_interactions ALTER COLUMN id SET DEFAULT nextval('public.micro_lesson_interactions_id_seq'::regclass);



ALTER TABLE ONLY public.micro_lesson_jobs ALTER COLUMN id SET DEFAULT nextval('public.micro_lesson_jobs_id_seq'::regclass);



ALTER TABLE ONLY public.micro_lessons ALTER COLUMN id SET DEFAULT nextval('public.micro_lessons_id_seq'::regclass);



ALTER TABLE ONLY public.micro_quiz_jobs ALTER COLUMN id SET DEFAULT nextval('public.micro_quiz_jobs_id_seq'::regclass);



ALTER TABLE ONLY public.micro_quizzes ALTER COLUMN id SET DEFAULT nextval('public.micro_quizzes_id_seq'::regclass);



ALTER TABLE ONLY public.organization_members ALTER COLUMN id SET DEFAULT nextval('public.organization_members_id_seq'::regclass);



ALTER TABLE ONLY public.organizations ALTER COLUMN id SET DEFAULT nextval('public.organizations_id_seq'::regclass);



ALTER TABLE ONLY public.permissions ALTER COLUMN id SET DEFAULT nextval('public.permissions_id_seq'::regclass);



ALTER TABLE ONLY public.question_bank_items ALTER COLUMN id SET DEFAULT nextval('public.question_bank_items_id_seq'::regclass);



ALTER TABLE ONLY public.question_skills ALTER COLUMN id SET DEFAULT nextval('public.question_skills_id_seq'::regclass);



ALTER TABLE ONLY public.quiz_analytics ALTER COLUMN id SET DEFAULT nextval('public.quiz_analytics_id_seq'::regclass);



ALTER TABLE ONLY public.quiz_answer_options ALTER COLUMN id SET DEFAULT nextval('public.quiz_answer_options_id_seq'::regclass);



ALTER TABLE ONLY public.quiz_attempts ALTER COLUMN id SET DEFAULT nextval('public.quiz_attempts_id_seq'::regclass);



ALTER TABLE ONLY public.quiz_correct_answers ALTER COLUMN id SET DEFAULT nextval('public.quiz_correct_answers_id_seq'::regclass);



ALTER TABLE ONLY public.quiz_questions ALTER COLUMN id SET DEFAULT nextval('public.quiz_questions_id_seq'::regclass);



ALTER TABLE ONLY public.quiz_student_answers ALTER COLUMN id SET DEFAULT nextval('public.quiz_student_answers_id_seq'::regclass);



ALTER TABLE ONLY public.quizzes ALTER COLUMN id SET DEFAULT nextval('public.quizzes_id_seq'::regclass);



ALTER TABLE ONLY public.role_definitions ALTER COLUMN id SET DEFAULT nextval('public.role_definitions_id_seq'::regclass);



ALTER TABLE ONLY public.section_content ALTER COLUMN id SET DEFAULT nextval('public.section_content_id_seq'::regclass);



ALTER TABLE ONLY public.section_overview_jobs ALTER COLUMN id SET DEFAULT nextval('public.section_overview_jobs_id_seq'::regclass);



ALTER TABLE ONLY public.section_overview_lessons ALTER COLUMN id SET DEFAULT nextval('public.section_overview_lessons_id_seq'::regclass);



ALTER TABLE ONLY public.section_overview_quizzes ALTER COLUMN id SET DEFAULT nextval('public.section_overview_quizzes_id_seq'::regclass);



ALTER TABLE ONLY public.skill_prerequisites ALTER COLUMN id SET DEFAULT nextval('public.skill_prerequisites_id_seq'::regclass);



ALTER TABLE ONLY public.skill_recommendations ALTER COLUMN id SET DEFAULT nextval('public.skill_recommendations_id_seq'::regclass);



ALTER TABLE ONLY public.skill_relationships ALTER COLUMN id SET DEFAULT nextval('public.skill_relationships_id_seq'::regclass);



ALTER TABLE ONLY public.skills ALTER COLUMN id SET DEFAULT nextval('public.skills_id_seq'::regclass);



ALTER TABLE ONLY public.user_roles ALTER COLUMN id SET DEFAULT nextval('public.user_roles_id_seq'::regclass);



ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);



ALTER TABLE ONLY public.bulk_enrollment_logs
    ADD CONSTRAINT bulk_enrollment_logs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.competency_frameworks
    ADD CONSTRAINT competency_frameworks_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.content_progress
    ADD CONSTRAINT content_progress_content_id_student_id_key UNIQUE (content_id, student_id);



ALTER TABLE ONLY public.content_progress
    ADD CONSTRAINT content_progress_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.content_skills
    ADD CONSTRAINT content_skills_content_id_skill_id_key UNIQUE (content_id, skill_id);



ALTER TABLE ONLY public.content_skills
    ADD CONSTRAINT content_skills_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.course_co_teachers
    ADD CONSTRAINT course_co_teachers_course_id_user_id_key UNIQUE (course_id, user_id);



ALTER TABLE ONLY public.course_co_teachers
    ADD CONSTRAINT course_co_teachers_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.course_competencies
    ADD CONSTRAINT course_competencies_course_id_skill_id_key UNIQUE (course_id, skill_id);



ALTER TABLE ONLY public.course_competencies
    ADD CONSTRAINT course_competencies_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.course_sections
    ADD CONSTRAINT course_sections_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.courses
    ADD CONSTRAINT courses_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.enrollments
    ADD CONSTRAINT enrollments_course_id_student_id_key UNIQUE (course_id, student_id);



ALTER TABLE ONLY public.enrollments
    ADD CONSTRAINT enrollments_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.farm_learning_attempts
    ADD CONSTRAINT farm_learning_attempts_pkey PRIMARY KEY (challenge_id);



ALTER TABLE ONLY public.forum_comments
    ADD CONSTRAINT forum_comments_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.forum_posts
    ADD CONSTRAINT forum_posts_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.forum_votes
    ADD CONSTRAINT forum_votes_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.forum_votes
    ADD CONSTRAINT forum_votes_user_id_votable_type_votable_id_key UNIQUE (user_id, votable_type, votable_id);



ALTER TABLE ONLY public.knowledge_node_mastery
    ADD CONSTRAINT knowledge_node_mastery_pkey PRIMARY KEY (user_id, course_id, node_id);



ALTER TABLE ONLY public.learner_skill_states
    ADD CONSTRAINT learner_skill_states_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.learner_skill_states
    ADD CONSTRAINT learner_skill_states_student_id_skill_id_key UNIQUE (student_id, skill_id);



ALTER TABLE ONLY public.learning_events
    ADD CONSTRAINT learning_events_event_id_key UNIQUE (event_id);



ALTER TABLE ONLY public.learning_events
    ADD CONSTRAINT learning_events_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.learning_notification_events
    ADD CONSTRAINT learning_notification_events_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.learning_notification_reads
    ADD CONSTRAINT learning_notification_reads_pkey PRIMARY KEY (user_id, notification_key);



ALTER TABLE ONLY public.lms_callback_receipts
    ADD CONSTRAINT lms_callback_receipts_pkey PRIMARY KEY (kind, job_id);



ALTER TABLE ONLY public.lms_file_assets
    ADD CONSTRAINT lms_file_assets_pkey PRIMARY KEY (file_path);



ALTER TABLE ONLY public.lms_processed_interactions
    ADD CONSTRAINT lms_processed_interactions_pkey PRIMARY KEY (interaction_id);



ALTER TABLE ONLY public.lms_quiz_effects
    ADD CONSTRAINT lms_quiz_effects_pkey PRIMARY KEY (attempt_id);



ALTER TABLE ONLY public.micro_lesson_interactions
    ADD CONSTRAINT micro_lesson_interactions_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.micro_lesson_jobs
    ADD CONSTRAINT micro_lesson_jobs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.micro_lessons
    ADD CONSTRAINT micro_lessons_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.micro_quiz_jobs
    ADD CONSTRAINT micro_quiz_jobs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.micro_quizzes
    ADD CONSTRAINT micro_quizzes_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.organization_members
    ADD CONSTRAINT organization_members_org_id_user_id_key UNIQUE (org_id, user_id);



ALTER TABLE ONLY public.organization_members
    ADD CONSTRAINT organization_members_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_slug_key UNIQUE (slug);



ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_code_key UNIQUE (code);



ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.question_bank_items
    ADD CONSTRAINT question_bank_items_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.question_skills
    ADD CONSTRAINT question_skills_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.question_skills
    ADD CONSTRAINT question_skills_question_id_skill_id_key UNIQUE (question_id, skill_id);



ALTER TABLE ONLY public.quiz_analytics
    ADD CONSTRAINT quiz_analytics_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.quiz_analytics
    ADD CONSTRAINT quiz_analytics_quiz_id_question_id_key UNIQUE (quiz_id, question_id);



ALTER TABLE ONLY public.quiz_answer_options
    ADD CONSTRAINT quiz_answer_options_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.quiz_attempts
    ADD CONSTRAINT quiz_attempts_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.quiz_attempts
    ADD CONSTRAINT quiz_attempts_quiz_id_student_id_attempt_number_key UNIQUE (quiz_id, student_id, attempt_number);



ALTER TABLE ONLY public.quiz_correct_answers
    ADD CONSTRAINT quiz_correct_answers_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.quiz_index_versions
    ADD CONSTRAINT quiz_index_versions_pkey PRIMARY KEY (quiz_id);



ALTER TABLE ONLY public.quiz_questions
    ADD CONSTRAINT quiz_questions_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.quiz_student_answers
    ADD CONSTRAINT quiz_student_answers_attempt_id_question_id_key UNIQUE (attempt_id, question_id);



ALTER TABLE ONLY public.quiz_student_answers
    ADD CONSTRAINT quiz_student_answers_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.quizzes
    ADD CONSTRAINT quizzes_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.role_definitions
    ADD CONSTRAINT role_definitions_name_key UNIQUE (name);



ALTER TABLE ONLY public.role_definitions
    ADD CONSTRAINT role_definitions_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_pkey PRIMARY KEY (role_id, permission_id);



ALTER TABLE ONLY public.section_content
    ADD CONSTRAINT section_content_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.section_overview_jobs
    ADD CONSTRAINT section_overview_jobs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.section_overview_lessons
    ADD CONSTRAINT section_overview_lessons_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.section_overview_quizzes
    ADD CONSTRAINT section_overview_quizzes_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.skill_prerequisites
    ADD CONSTRAINT skill_prerequisites_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.skill_prerequisites
    ADD CONSTRAINT skill_prerequisites_skill_id_prerequisite_skill_id_key UNIQUE (skill_id, prerequisite_skill_id);



ALTER TABLE ONLY public.skill_recommendations
    ADD CONSTRAINT skill_recommendations_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.skill_recommendations
    ADD CONSTRAINT skill_recommendations_recommendation_id_key UNIQUE (recommendation_id);



ALTER TABLE ONLY public.skill_relationships
    ADD CONSTRAINT skill_relationships_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.skill_relationships
    ADD CONSTRAINT skill_relationships_source_skill_id_target_skill_id_relatio_key UNIQUE (source_skill_id, target_skill_id, relationship_type);



ALTER TABLE ONLY public.skills
    ADD CONSTRAINT skills_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_user_id_role_key UNIQUE (user_id, role);



ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);



ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);



CREATE INDEX farm_learning_attempts_user_course_idx ON public.farm_learning_attempts USING btree (user_id, course_id, created_at DESC);



CREATE INDEX idx_answer_options_blank ON public.quiz_answer_options USING btree (question_id, blank_id);



CREATE INDEX idx_answer_options_blank_id ON public.quiz_answer_options USING btree (blank_id) WHERE (blank_id IS NOT NULL);



CREATE INDEX idx_answer_options_question ON public.quiz_answer_options USING btree (question_id);



CREATE INDEX idx_bulk_logs_course ON public.bulk_enrollment_logs USING btree (course_id);



CREATE INDEX idx_bulk_logs_status ON public.bulk_enrollment_logs USING btree (status);



CREATE INDEX idx_bulk_logs_teacher ON public.bulk_enrollment_logs USING btree (teacher_id);



CREATE INDEX idx_co_teachers_course ON public.course_co_teachers USING btree (course_id);



CREATE INDEX idx_co_teachers_user ON public.course_co_teachers USING btree (user_id);



CREATE INDEX idx_competency_frameworks_organization ON public.competency_frameworks USING btree (organization_id, status);



CREATE INDEX idx_content_ai_status ON public.section_content USING btree (ai_index_status) WHERE ((ai_index_status)::text = ANY (ARRAY[('processing'::character varying)::text, ('indexed'::character varying)::text]));



CREATE INDEX idx_content_order ON public.section_content USING btree (section_id, order_index);



CREATE INDEX idx_content_progress_content ON public.content_progress USING btree (content_id);



CREATE INDEX idx_content_progress_content_student ON public.content_progress USING btree (content_id, student_id) INCLUDE (completed_at);



CREATE INDEX idx_content_progress_student ON public.content_progress USING btree (student_id);



CREATE INDEX idx_content_progress_student_content ON public.content_progress USING btree (student_id, content_id);



CREATE INDEX idx_content_progress_student_course ON public.content_progress USING btree (student_id, content_id);



CREATE INDEX idx_content_section ON public.section_content USING btree (section_id);



CREATE INDEX idx_content_skills_content ON public.content_skills USING btree (content_id);



CREATE INDEX idx_content_skills_skill ON public.content_skills USING btree (skill_id);



CREATE INDEX idx_content_type ON public.section_content USING btree (type);



CREATE INDEX idx_correct_answers_blank_id ON public.quiz_correct_answers USING btree (blank_id) WHERE (blank_id IS NOT NULL);



CREATE INDEX idx_correct_answers_question ON public.quiz_correct_answers USING btree (question_id);



CREATE INDEX idx_course_competencies_course ON public.course_competencies USING btree (course_id);



CREATE INDEX idx_course_competencies_skill ON public.course_competencies USING btree (skill_id);



CREATE INDEX idx_courses_category ON public.courses USING btree (category);



CREATE INDEX idx_courses_created_by ON public.courses USING btree (created_by);



CREATE INDEX idx_courses_creator_created_page ON public.courses USING btree (created_by, created_at DESC, id DESC);



CREATE INDEX idx_courses_level ON public.courses USING btree (level);



CREATE INDEX idx_courses_org_published_page ON public.courses USING btree (org_id, published_at DESC, id DESC) WHERE ((status)::text = 'PUBLISHED'::text);



CREATE INDEX idx_courses_org_status_pub ON public.courses USING btree (org_id, status, published_at DESC) WHERE ((status)::text = 'PUBLISHED'::text);



CREATE INDEX idx_courses_org_visibility_status ON public.courses USING btree (org_id, visibility, status);



CREATE INDEX idx_courses_published_page ON public.courses USING btree (published_at DESC, id DESC) WHERE ((status)::text = 'PUBLISHED'::text);



CREATE INDEX idx_courses_status ON public.courses USING btree (status);



CREATE INDEX idx_courses_teacher_published ON public.courses USING btree (created_by, id) WHERE ((status)::text = 'PUBLISHED'::text);



CREATE INDEX idx_enrollments_accepted_timeline ON public.enrollments USING btree (course_id, enrolled_at DESC, student_id) WHERE ((status)::text = 'ACCEPTED'::text);



CREATE INDEX idx_enrollments_course ON public.enrollments USING btree (course_id);



CREATE INDEX idx_enrollments_course_accepted ON public.enrollments USING btree (course_id, student_id) WHERE ((status)::text = 'ACCEPTED'::text);



CREATE INDEX idx_enrollments_course_status ON public.enrollments USING btree (course_id, status);



CREATE INDEX idx_enrollments_status ON public.enrollments USING btree (status);



CREATE INDEX idx_enrollments_student ON public.enrollments USING btree (student_id);



CREATE INDEX idx_enrollments_student_status ON public.enrollments USING btree (student_id, status);



CREATE INDEX idx_forum_comments_accepted ON public.forum_comments USING btree (post_id, is_accepted DESC);



CREATE INDEX idx_forum_comments_parent ON public.forum_comments USING btree (parent_comment_id);



CREATE INDEX idx_forum_comments_post ON public.forum_comments USING btree (post_id);



CREATE INDEX idx_forum_comments_user ON public.forum_comments USING btree (user_id);



CREATE INDEX idx_forum_posts_content ON public.forum_posts USING btree (content_id);



CREATE INDEX idx_forum_posts_created ON public.forum_posts USING btree (content_id, created_at DESC);



CREATE INDEX idx_forum_posts_pinned ON public.forum_posts USING btree (content_id, is_pinned DESC, created_at DESC);



CREATE INDEX idx_forum_posts_score ON public.forum_posts USING btree (content_id, ((upvotes - downvotes)) DESC, created_at DESC) WHERE (is_pinned = false);



CREATE INDEX idx_forum_posts_search ON public.forum_posts USING gin (to_tsvector('english'::regconfig, (((title)::text || ' '::text) || body)));



CREATE INDEX idx_forum_posts_tags ON public.forum_posts USING gin (tags);



CREATE INDEX idx_forum_posts_user ON public.forum_posts USING btree (user_id);



CREATE INDEX idx_forum_votes_user ON public.forum_votes USING btree (user_id);



CREATE INDEX idx_forum_votes_votable ON public.forum_votes USING btree (votable_type, votable_id);



CREATE INDEX idx_knm_course_node ON public.knowledge_node_mastery USING btree (course_id, node_id);



CREATE INDEX idx_knm_user_course ON public.knowledge_node_mastery USING btree (user_id, course_id);



CREATE INDEX idx_learner_skill_states_last_practiced ON public.learner_skill_states USING btree (last_practiced_at DESC);



CREATE INDEX idx_learner_skill_states_mastery ON public.learner_skill_states USING btree (mastery_score);



CREATE INDEX idx_learner_skill_states_skill ON public.learner_skill_states USING btree (skill_id, mastery_score DESC);



CREATE INDEX idx_learner_skill_states_student ON public.learner_skill_states USING btree (student_id, mastery_score DESC);



CREATE INDEX idx_learning_events_course ON public.learning_events USING btree (course_id, student_id);



CREATE INDEX idx_learning_events_session ON public.learning_events USING btree (session_id);



CREATE INDEX idx_learning_events_skill ON public.learning_events USING btree (skill_id, student_id);



CREATE INDEX idx_learning_events_student ON public.learning_events USING btree (student_id, created_at DESC);



CREATE INDEX idx_learning_events_type ON public.learning_events USING btree (event_type, created_at DESC);



CREATE INDEX idx_learning_notification_reads_expiry ON public.learning_notification_reads USING btree (read_at);



CREATE INDEX idx_learning_notification_reads_time ON public.learning_notification_reads USING btree (user_id, read_at DESC);



CREATE INDEX idx_learning_notifications_course ON public.learning_notification_events USING btree (course_id, created_at DESC);



CREATE INDEX idx_learning_notifications_created ON public.learning_notification_events USING btree (created_at);



CREATE INDEX idx_learning_notifications_pending ON public.learning_notification_events USING btree (id) WHERE (delivered_at IS NULL);



CREATE INDEX idx_lms_file_assets_owner ON public.lms_file_assets USING btree (owner_user_id);



CREATE INDEX idx_lms_quiz_effects_local ON public.lms_quiz_effects USING btree (attempt_id) WHERE (local_completed_at IS NULL);



CREATE INDEX idx_lms_quiz_effects_pending ON public.lms_quiz_effects USING btree (available_at) WHERE (completed_at IS NULL);



CREATE INDEX idx_micro_jobs_course ON public.micro_lesson_jobs USING btree (course_id);



CREATE INDEX idx_micro_jobs_creator ON public.micro_lesson_jobs USING btree (created_by);



CREATE INDEX idx_micro_jobs_status ON public.micro_lesson_jobs USING btree (status);



CREATE INDEX idx_micro_lessons_course ON public.micro_lessons USING btree (course_id);



CREATE INDEX idx_micro_lessons_job ON public.micro_lessons USING btree (job_id);



CREATE INDEX idx_micro_lessons_node_id ON public.micro_lessons USING btree (node_id);



CREATE INDEX idx_micro_lessons_order ON public.micro_lessons USING btree (job_id, order_index);



CREATE INDEX idx_micro_lessons_section ON public.micro_lessons USING btree (section_id);



CREATE INDEX idx_micro_lessons_source ON public.micro_lessons USING btree (source_content_id);



CREATE INDEX idx_micro_lessons_status ON public.micro_lessons USING btree (status);



CREATE INDEX idx_mli_action ON public.micro_lesson_interactions USING btree (action_type);



CREATE INDEX idx_mli_created_at ON public.micro_lesson_interactions USING btree (created_at DESC);



CREATE INDEX idx_mli_lesson ON public.micro_lesson_interactions USING btree (lesson_id);



CREATE INDEX idx_mli_node ON public.micro_lesson_interactions USING btree (node_id);



CREATE INDEX idx_mli_user_course ON public.micro_lesson_interactions USING btree (user_id, course_id);



CREATE INDEX idx_mq_course ON public.micro_quizzes USING btree (course_id);



CREATE INDEX idx_mq_job ON public.micro_quizzes USING btree (job_id);



CREATE INDEX idx_mq_node_id ON public.micro_quizzes USING btree (node_id);



CREATE INDEX idx_mq_order ON public.micro_quizzes USING btree (job_id, order_index);



CREATE INDEX idx_mq_section ON public.micro_quizzes USING btree (section_id);



CREATE INDEX idx_mq_source ON public.micro_quizzes USING btree (source_content_id);



CREATE INDEX idx_mq_status ON public.micro_quizzes USING btree (status);



CREATE INDEX idx_mqj_course ON public.micro_quiz_jobs USING btree (course_id);



CREATE INDEX idx_mqj_creator ON public.micro_quiz_jobs USING btree (created_by);



CREATE INDEX idx_mqj_status ON public.micro_quiz_jobs USING btree (status);



CREATE INDEX idx_org_members_org_id ON public.organization_members USING btree (org_id);



CREATE INDEX idx_org_members_user_id ON public.organization_members USING btree (user_id);



CREATE INDEX idx_organizations_is_active ON public.organizations USING btree (is_active);



CREATE INDEX idx_qbank_course_bloom ON public.question_bank_items USING btree (course_id, bloom_level);



CREATE INDEX idx_qbank_course_created ON public.question_bank_items USING btree (course_id, created_at DESC, id DESC);



CREATE INDEX idx_qbank_course_difficulty ON public.question_bank_items USING btree (course_id, difficulty);



CREATE INDEX idx_qbank_course_node ON public.question_bank_items USING btree (course_id, node_id);



CREATE INDEX idx_qbank_fts ON public.question_bank_items USING gin (to_tsvector('simple'::regconfig, question_text));



CREATE INDEX idx_question_skills_question ON public.question_skills USING btree (question_id);



CREATE INDEX idx_question_skills_skill ON public.question_skills USING btree (skill_id);



CREATE INDEX idx_quiz_analytics_question ON public.quiz_analytics USING btree (question_id);



CREATE INDEX idx_quiz_analytics_quiz ON public.quiz_analytics USING btree (quiz_id);



CREATE INDEX idx_quiz_attempts_analytics ON public.quiz_attempts USING btree (quiz_id, student_id, status, percentage, is_passed) WHERE ((status)::text = ANY (ARRAY[('SUBMITTED'::character varying)::text, ('GRADED'::character varying)::text]));



CREATE INDEX idx_quiz_attempts_dashboard_first ON public.quiz_attempts USING btree (quiz_id, student_id, attempt_number, id) INCLUDE (percentage) WHERE ((status)::text = ANY (ARRAY[('SUBMITTED'::character varying)::text, ('GRADED'::character varying)::text]));



CREATE INDEX idx_quiz_attempts_quiz ON public.quiz_attempts USING btree (quiz_id);



CREATE INDEX idx_quiz_attempts_quiz_student ON public.quiz_attempts USING btree (quiz_id, student_id);



CREATE INDEX idx_quiz_attempts_status ON public.quiz_attempts USING btree (status);



CREATE INDEX idx_quiz_attempts_student ON public.quiz_attempts USING btree (student_id);



CREATE INDEX idx_quiz_attempts_student_status ON public.quiz_attempts USING btree (student_id, quiz_id, status, submitted_at) WHERE ((status)::text = ANY (ARRAY[('SUBMITTED'::character varying)::text, ('GRADED'::character varying)::text]));



CREATE INDEX idx_quiz_questions_bloom ON public.quiz_questions USING btree (bloom_level) WHERE (bloom_level IS NOT NULL);



CREATE INDEX idx_quiz_questions_node ON public.quiz_questions USING btree (node_id) WHERE (node_id IS NOT NULL);



CREATE INDEX idx_quiz_questions_order ON public.quiz_questions USING btree (quiz_id, order_index);



CREATE INDEX idx_quiz_questions_quiz ON public.quiz_questions USING btree (quiz_id);



CREATE INDEX idx_quiz_questions_quiz_order ON public.quiz_questions USING btree (quiz_id, order_index) INCLUDE (points, question_type, node_id);



CREATE INDEX idx_quiz_questions_settings ON public.quiz_questions USING gin (settings);



CREATE INDEX idx_quiz_questions_type ON public.quiz_questions USING btree (question_type);



CREATE INDEX idx_quizzes_available ON public.quizzes USING btree (available_from, available_until);



CREATE INDEX idx_quizzes_content ON public.quizzes USING btree (content_id);



CREATE INDEX idx_quizzes_published ON public.quizzes USING btree (is_published);



CREATE INDEX idx_role_permissions_role ON public.role_permissions USING btree (role_id);



CREATE INDEX idx_section_content_section_mandatory ON public.section_content USING btree (section_id, id, is_mandatory) WHERE (is_mandatory = true);



CREATE INDEX idx_sections_course ON public.course_sections USING btree (course_id);



CREATE INDEX idx_sections_order ON public.course_sections USING btree (course_id, order_index);



CREATE INDEX idx_skill_prerequisites_prerequisite ON public.skill_prerequisites USING btree (prerequisite_skill_id);



CREATE INDEX idx_skill_prerequisites_skill ON public.skill_prerequisites USING btree (skill_id);



CREATE INDEX idx_skill_recommendations_clicked ON public.skill_recommendations USING btree (clicked, created_at DESC);



CREATE INDEX idx_skill_recommendations_completed ON public.skill_recommendations USING btree (completed, created_at DESC);



CREATE INDEX idx_skill_recommendations_recommendation_id ON public.skill_recommendations USING btree (recommendation_id);



CREATE INDEX idx_skill_recommendations_student ON public.skill_recommendations USING btree (student_id, created_at DESC);



CREATE INDEX idx_skill_relationships_source ON public.skill_relationships USING btree (source_skill_id, relationship_type);



CREATE INDEX idx_skill_relationships_target ON public.skill_relationships USING btree (target_skill_id, relationship_type);



CREATE INDEX idx_skills_framework ON public.skills USING btree (framework_id, status);



CREATE INDEX idx_skills_parent ON public.skills USING btree (parent_skill_id);



CREATE INDEX idx_sov_jobs_course ON public.section_overview_jobs USING btree (course_id);



CREATE INDEX idx_sov_jobs_section ON public.section_overview_jobs USING btree (section_id);



CREATE INDEX idx_sov_lessons_job ON public.section_overview_lessons USING btree (job_id);



CREATE INDEX idx_sov_quizzes_job ON public.section_overview_quizzes USING btree (job_id);



CREATE INDEX idx_student_answers_attempt ON public.quiz_student_answers USING btree (attempt_id);



CREATE INDEX idx_student_answers_attempt_grading ON public.quiz_student_answers USING btree (attempt_id, is_correct, points_earned) WHERE (is_correct IS NOT NULL);



CREATE INDEX idx_student_answers_data ON public.quiz_student_answers USING gin (answer_data);



CREATE INDEX idx_student_answers_question ON public.quiz_student_answers USING btree (question_id);



CREATE INDEX idx_student_answers_ungraded ON public.quiz_student_answers USING btree (attempt_id, question_id) WHERE (points_earned IS NULL);



CREATE INDEX idx_user_roles_role ON public.user_roles USING btree (role);



CREATE INDEX idx_user_roles_user ON public.user_roles USING btree (user_id);



CREATE INDEX idx_users_email ON public.users USING btree (email);



CREATE INDEX quiz_questions_index_cursor ON public.quiz_questions USING btree (quiz_id, id);



CREATE UNIQUE INDEX uq_competency_frameworks_global_code ON public.competency_frameworks USING btree (code) WHERE (organization_id IS NULL);



CREATE UNIQUE INDEX uq_competency_frameworks_org_code ON public.competency_frameworks USING btree (organization_id, code) WHERE (organization_id IS NOT NULL);



CREATE UNIQUE INDEX uq_qbank_course_qtext ON public.question_bank_items USING btree (course_id, md5(btrim(question_text)));



CREATE UNIQUE INDEX uq_skills_framework_code ON public.skills USING btree (framework_id, code) WHERE ((framework_id IS NOT NULL) AND (code IS NOT NULL));



CREATE UNIQUE INDEX uq_skills_global_code ON public.skills USING btree (code) WHERE ((framework_id IS NULL) AND (code IS NOT NULL));



CREATE OR REPLACE VIEW public.quiz_summary_view AS
 SELECT q.id,
    q.content_id,
    q.title,
    q.description,
    q.instructions,
    q.time_limit_minutes,
    q.available_from,
    q.available_until,
    q.max_attempts,
    q.shuffle_questions,
    q.shuffle_answers,
    q.passing_score,
    q.total_points,
    q.auto_grade,
    q.show_results_immediately,
    q.show_correct_answers,
    q.allow_review,
    q.show_feedback,
    q.is_published,
    q.created_by,
    q.created_at,
    q.updated_at,
    u.full_name AS creator_name,
    u.email AS creator_email,
    count(DISTINCT qq.id) AS question_count,
    count(DISTINCT qa.id) AS attempt_count,
    count(DISTINCT qa.student_id) AS student_count,
    avg(qa.percentage) AS average_score,
    count(DISTINCT qa.id) FILTER (WHERE (qa.is_passed = true)) AS passed_count
   FROM (((public.quizzes q
     LEFT JOIN public.users u ON ((q.created_by = u.id)))
     LEFT JOIN public.quiz_questions qq ON ((q.id = qq.quiz_id)))
     LEFT JOIN public.quiz_attempts qa ON (((q.id = qa.quiz_id) AND ((qa.status)::text = 'GRADED'::text))))
  GROUP BY q.id, u.full_name, u.email;



CREATE TRIGGER capture_content_notification AFTER INSERT OR DELETE OR UPDATE ON public.section_content FOR EACH ROW EXECUTE FUNCTION public.capture_learning_notification();



CREATE TRIGGER capture_course_notification AFTER INSERT OR UPDATE ON public.courses FOR EACH ROW EXECUTE FUNCTION public.capture_learning_notification();



CREATE TRIGGER capture_quiz_learning_notification AFTER INSERT OR UPDATE ON public.quizzes FOR EACH ROW EXECUTE FUNCTION public.capture_quiz_learning_notification();



CREATE TRIGGER capture_section_notification AFTER INSERT OR DELETE OR UPDATE ON public.course_sections FOR EACH ROW EXECUTE FUNCTION public.capture_learning_notification();



CREATE TRIGGER enforce_learning_publication BEFORE INSERT OR UPDATE ON public.course_sections FOR EACH ROW EXECUTE FUNCTION public.enforce_learning_publication();



CREATE TRIGGER enforce_learning_publication BEFORE INSERT OR UPDATE ON public.quizzes FOR EACH ROW EXECUTE FUNCTION public.enforce_learning_publication();



CREATE TRIGGER enforce_learning_publication BEFORE INSERT OR UPDATE ON public.section_content FOR EACH ROW EXECUTE FUNCTION public.enforce_learning_publication();



CREATE TRIGGER quiz_answer_assessment_snapshot BEFORE INSERT ON public.quiz_student_answers FOR EACH ROW EXECUTE FUNCTION public.capture_quiz_assessment_snapshot();



CREATE TRIGGER quiz_option_index_version AFTER INSERT OR DELETE OR UPDATE ON public.quiz_answer_options FOR EACH ROW EXECUTE FUNCTION public.track_quiz_option_index();



CREATE TRIGGER quiz_question_index_version AFTER INSERT OR DELETE OR UPDATE ON public.quiz_questions FOR EACH ROW EXECUTE FUNCTION public.track_quiz_question_index();



CREATE TRIGGER trigger_auto_accept_enrollment BEFORE INSERT ON public.enrollments FOR EACH ROW EXECUTE FUNCTION public.auto_accept_enrollment();



CREATE TRIGGER trigger_reset_ai_index_timestamp BEFORE UPDATE OF ai_index_status ON public.section_content FOR EACH ROW EXECUTE FUNCTION public.reset_ai_index_timestamp();



CREATE TRIGGER trigger_update_post_comment_count AFTER INSERT OR DELETE ON public.forum_comments FOR EACH ROW EXECUTE FUNCTION public.update_post_comment_count();



CREATE TRIGGER trigger_update_vote_counts AFTER INSERT OR DELETE OR UPDATE ON public.forum_votes FOR EACH ROW EXECUTE FUNCTION public.update_vote_counts();



CREATE TRIGGER update_competency_frameworks_updated_at BEFORE UPDATE ON public.competency_frameworks FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_course_sections_updated_at BEFORE UPDATE ON public.course_sections FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_courses_updated_at BEFORE UPDATE ON public.courses FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_enrollments_updated_at BEFORE UPDATE ON public.enrollments FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_forum_comments_updated_at BEFORE UPDATE ON public.forum_comments FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_forum_posts_updated_at BEFORE UPDATE ON public.forum_posts FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_learner_skill_states_updated_at BEFORE UPDATE ON public.learner_skill_states FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_micro_lesson_jobs_updated_at BEFORE UPDATE ON public.micro_lesson_jobs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_micro_lessons_updated_at BEFORE UPDATE ON public.micro_lessons FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_micro_quiz_jobs_updated_at BEFORE UPDATE ON public.micro_quiz_jobs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_micro_quizzes_updated_at BEFORE UPDATE ON public.micro_quizzes FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_quiz_attempts_updated_at BEFORE UPDATE ON public.quiz_attempts FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_quiz_questions_updated_at BEFORE UPDATE ON public.quiz_questions FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_quiz_student_answers_updated_at BEFORE UPDATE ON public.quiz_student_answers FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_quizzes_updated_at BEFORE UPDATE ON public.quizzes FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_section_content_updated_at BEFORE UPDATE ON public.section_content FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_skills_updated_at BEFORE UPDATE ON public.skills FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();



ALTER TABLE ONLY public.bulk_enrollment_logs
    ADD CONSTRAINT bulk_enrollment_logs_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.competency_frameworks
    ADD CONSTRAINT competency_frameworks_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.competency_frameworks
    ADD CONSTRAINT competency_frameworks_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.content_progress
    ADD CONSTRAINT content_progress_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.section_content(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.content_progress
    ADD CONSTRAINT content_progress_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.content_skills
    ADD CONSTRAINT content_skills_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.section_content(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.content_skills
    ADD CONSTRAINT content_skills_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skills(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.course_co_teachers
    ADD CONSTRAINT course_co_teachers_added_by_fkey FOREIGN KEY (added_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.course_co_teachers
    ADD CONSTRAINT course_co_teachers_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.course_co_teachers
    ADD CONSTRAINT course_co_teachers_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.course_competencies
    ADD CONSTRAINT course_competencies_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.course_competencies
    ADD CONSTRAINT course_competencies_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skills(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.course_sections
    ADD CONSTRAINT course_sections_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.courses
    ADD CONSTRAINT courses_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.courses
    ADD CONSTRAINT courses_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id);



ALTER TABLE ONLY public.enrollments
    ADD CONSTRAINT enrollments_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.farm_learning_attempts
    ADD CONSTRAINT farm_learning_attempts_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.farm_learning_attempts
    ADD CONSTRAINT farm_learning_attempts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.forum_comments
    ADD CONSTRAINT forum_comments_parent_comment_id_fkey FOREIGN KEY (parent_comment_id) REFERENCES public.forum_comments(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.forum_comments
    ADD CONSTRAINT forum_comments_post_id_fkey FOREIGN KEY (post_id) REFERENCES public.forum_posts(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.forum_comments
    ADD CONSTRAINT forum_comments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.forum_posts
    ADD CONSTRAINT forum_posts_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.section_content(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.forum_posts
    ADD CONSTRAINT forum_posts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.forum_votes
    ADD CONSTRAINT forum_votes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.knowledge_node_mastery
    ADD CONSTRAINT knowledge_node_mastery_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.knowledge_node_mastery
    ADD CONSTRAINT knowledge_node_mastery_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.learner_skill_states
    ADD CONSTRAINT learner_skill_states_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skills(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.learner_skill_states
    ADD CONSTRAINT learner_skill_states_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.learning_events
    ADD CONSTRAINT learning_events_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.learning_events
    ADD CONSTRAINT learning_events_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.quiz_questions(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.learning_events
    ADD CONSTRAINT learning_events_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skills(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.learning_events
    ADD CONSTRAINT learning_events_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.learning_notification_reads
    ADD CONSTRAINT learning_notification_reads_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.lms_quiz_effects
    ADD CONSTRAINT lms_quiz_effects_attempt_id_fkey FOREIGN KEY (attempt_id) REFERENCES public.quiz_attempts(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.micro_lesson_interactions
    ADD CONSTRAINT micro_lesson_interactions_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.micro_lesson_interactions
    ADD CONSTRAINT micro_lesson_interactions_lesson_id_fkey FOREIGN KEY (lesson_id) REFERENCES public.micro_lessons(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.micro_lesson_interactions
    ADD CONSTRAINT micro_lesson_interactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.micro_lesson_jobs
    ADD CONSTRAINT micro_lesson_jobs_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.micro_lesson_jobs
    ADD CONSTRAINT micro_lesson_jobs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.micro_lesson_jobs
    ADD CONSTRAINT micro_lesson_jobs_section_id_fkey FOREIGN KEY (section_id) REFERENCES public.course_sections(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.micro_lesson_jobs
    ADD CONSTRAINT micro_lesson_jobs_source_content_id_fkey FOREIGN KEY (source_content_id) REFERENCES public.section_content(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.micro_lessons
    ADD CONSTRAINT micro_lessons_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.micro_lessons
    ADD CONSTRAINT micro_lessons_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.micro_lessons
    ADD CONSTRAINT micro_lessons_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.micro_lesson_jobs(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.micro_lessons
    ADD CONSTRAINT micro_lessons_published_content_id_fkey FOREIGN KEY (published_content_id) REFERENCES public.section_content(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.micro_lessons
    ADD CONSTRAINT micro_lessons_section_id_fkey FOREIGN KEY (section_id) REFERENCES public.course_sections(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.micro_lessons
    ADD CONSTRAINT micro_lessons_source_content_id_fkey FOREIGN KEY (source_content_id) REFERENCES public.section_content(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.micro_quiz_jobs
    ADD CONSTRAINT micro_quiz_jobs_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.micro_quiz_jobs
    ADD CONSTRAINT micro_quiz_jobs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.micro_quiz_jobs
    ADD CONSTRAINT micro_quiz_jobs_section_id_fkey FOREIGN KEY (section_id) REFERENCES public.course_sections(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.micro_quiz_jobs
    ADD CONSTRAINT micro_quiz_jobs_source_content_id_fkey FOREIGN KEY (source_content_id) REFERENCES public.section_content(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.micro_quizzes
    ADD CONSTRAINT micro_quizzes_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.micro_quizzes
    ADD CONSTRAINT micro_quizzes_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.micro_quizzes
    ADD CONSTRAINT micro_quizzes_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.micro_quiz_jobs(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.micro_quizzes
    ADD CONSTRAINT micro_quizzes_published_content_id_fkey FOREIGN KEY (published_content_id) REFERENCES public.section_content(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.micro_quizzes
    ADD CONSTRAINT micro_quizzes_section_id_fkey FOREIGN KEY (section_id) REFERENCES public.course_sections(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.micro_quizzes
    ADD CONSTRAINT micro_quizzes_source_content_id_fkey FOREIGN KEY (source_content_id) REFERENCES public.section_content(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.organization_members
    ADD CONSTRAINT organization_members_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.organization_members
    ADD CONSTRAINT organization_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.question_bank_items
    ADD CONSTRAINT question_bank_items_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.question_bank_items
    ADD CONSTRAINT question_bank_items_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.question_bank_items
    ADD CONSTRAINT question_bank_items_source_quiz_id_fkey FOREIGN KEY (source_quiz_id) REFERENCES public.quizzes(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.question_skills
    ADD CONSTRAINT question_skills_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.quiz_questions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.question_skills
    ADD CONSTRAINT question_skills_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skills(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.quiz_analytics
    ADD CONSTRAINT quiz_analytics_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.quiz_questions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.quiz_analytics
    ADD CONSTRAINT quiz_analytics_quiz_id_fkey FOREIGN KEY (quiz_id) REFERENCES public.quizzes(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.quiz_answer_options
    ADD CONSTRAINT quiz_answer_options_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.quiz_questions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.quiz_attempts
    ADD CONSTRAINT quiz_attempts_graded_by_fkey FOREIGN KEY (graded_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.quiz_attempts
    ADD CONSTRAINT quiz_attempts_quiz_id_fkey FOREIGN KEY (quiz_id) REFERENCES public.quizzes(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.quiz_attempts
    ADD CONSTRAINT quiz_attempts_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.quiz_correct_answers
    ADD CONSTRAINT quiz_correct_answers_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.quiz_questions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.quiz_index_versions
    ADD CONSTRAINT quiz_index_versions_quiz_id_fkey FOREIGN KEY (quiz_id) REFERENCES public.quizzes(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.quiz_questions
    ADD CONSTRAINT quiz_questions_quiz_id_fkey FOREIGN KEY (quiz_id) REFERENCES public.quizzes(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.quiz_student_answers
    ADD CONSTRAINT quiz_student_answers_attempt_id_fkey FOREIGN KEY (attempt_id) REFERENCES public.quiz_attempts(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.quiz_student_answers
    ADD CONSTRAINT quiz_student_answers_graded_by_fkey FOREIGN KEY (graded_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.quiz_student_answers
    ADD CONSTRAINT quiz_student_answers_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.quiz_questions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.quizzes
    ADD CONSTRAINT quizzes_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.section_content(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.quizzes
    ADD CONSTRAINT quizzes_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_permission_id_fkey FOREIGN KEY (permission_id) REFERENCES public.permissions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.role_definitions(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.section_content
    ADD CONSTRAINT section_content_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);



ALTER TABLE ONLY public.section_content
    ADD CONSTRAINT section_content_section_id_fkey FOREIGN KEY (section_id) REFERENCES public.course_sections(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.section_overview_lessons
    ADD CONSTRAINT section_overview_lessons_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.section_overview_jobs(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.section_overview_quizzes
    ADD CONSTRAINT section_overview_quizzes_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.section_overview_jobs(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.skill_prerequisites
    ADD CONSTRAINT skill_prerequisites_prerequisite_skill_id_fkey FOREIGN KEY (prerequisite_skill_id) REFERENCES public.skills(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.skill_prerequisites
    ADD CONSTRAINT skill_prerequisites_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skills(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.skill_recommendations
    ADD CONSTRAINT skill_recommendations_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.section_content(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.skill_recommendations
    ADD CONSTRAINT skill_recommendations_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.skill_recommendations
    ADD CONSTRAINT skill_recommendations_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skills(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.skill_recommendations
    ADD CONSTRAINT skill_recommendations_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.users(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.skill_relationships
    ADD CONSTRAINT skill_relationships_source_skill_id_fkey FOREIGN KEY (source_skill_id) REFERENCES public.skills(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.skill_relationships
    ADD CONSTRAINT skill_relationships_target_skill_id_fkey FOREIGN KEY (target_skill_id) REFERENCES public.skills(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.skills
    ADD CONSTRAINT skills_framework_id_fkey FOREIGN KEY (framework_id) REFERENCES public.competency_frameworks(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.skills
    ADD CONSTRAINT skills_parent_skill_id_fkey FOREIGN KEY (parent_skill_id) REFERENCES public.skills(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Default rows from repository SQL only.
SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;





INSERT INTO public.organizations VALUES (1, 'Big Data Club', 'bdc', 'Default organization', NULL, true, '{"allow_cross_org_courses": true, "default_course_visibility": "PUBLIC"}', NULL, '2026-11-27 05:57:44.985991', '2026-11-27 05:57:44.985991');






































































































INSERT INTO public.permissions VALUES (1, 'COURSE_VIEW', 'COURSE', 'View course details and content', '2026-11-27 05:57:44.877094');
INSERT INTO public.permissions VALUES (2, 'COURSE_CREATE', 'COURSE', 'Create new courses', '2026-11-27 05:57:44.877094');
INSERT INTO public.permissions VALUES (3, 'COURSE_EDIT', 'COURSE', 'Edit existing courses', '2026-11-27 05:57:44.877094');
INSERT INTO public.permissions VALUES (4, 'COURSE_DELETE', 'COURSE', 'Delete courses', '2026-11-27 05:57:44.877094');
INSERT INTO public.permissions VALUES (5, 'COURSE_PUBLISH', 'COURSE', 'Publish or unpublish courses', '2026-11-27 05:57:44.877094');
INSERT INTO public.permissions VALUES (6, 'QUIZ_CREATE', 'QUIZ', 'Create quizzes and questions', '2026-11-27 05:57:44.877094');
INSERT INTO public.permissions VALUES (7, 'QUIZ_EDIT', 'QUIZ', 'Edit existing quizzes', '2026-11-27 05:57:44.877094');
INSERT INTO public.permissions VALUES (8, 'QUIZ_DELETE', 'QUIZ', 'Delete quizzes', '2026-11-27 05:57:44.877094');
INSERT INTO public.permissions VALUES (9, 'QUIZ_GRADE', 'QUIZ', 'Grade quiz attempts', '2026-11-27 05:57:44.877094');
INSERT INTO public.permissions VALUES (10, 'ENROLLMENT_MANAGE', 'ENROLLMENT', 'Approve or reject enrollments', '2026-11-27 05:57:44.877094');
INSERT INTO public.permissions VALUES (11, 'ENROLLMENT_BULK', 'ENROLLMENT', 'Bulk enroll students', '2026-11-27 05:57:44.877094');
INSERT INTO public.permissions VALUES (12, 'AI_INDEX', 'AI', 'Trigger document AI indexing', '2026-11-27 05:57:44.877094');
INSERT INTO public.permissions VALUES (13, 'AI_GENERATE', 'AI', 'Generate AI content (lessons, quizzes)', '2026-11-27 05:57:44.877094');
INSERT INTO public.permissions VALUES (14, 'ROLE_MANAGE', 'SYSTEM', 'Manage roles and permissions', '2026-11-27 05:57:44.877094');
INSERT INTO public.permissions VALUES (15, 'ANALYTICS_VIEW', 'SYSTEM', 'View analytics and reports', '2026-11-27 05:57:44.877094');
























INSERT INTO public.role_definitions VALUES (1, 'STUDENT', 'Student', NULL, true, '2026-11-27 05:57:44.665632');
INSERT INTO public.role_definitions VALUES (2, 'TEACHER', 'Teacher', NULL, true, '2026-11-27 05:57:44.665632');
INSERT INTO public.role_definitions VALUES (3, 'ADMIN', 'Administrator', NULL, true, '2026-11-27 05:57:44.665632');



INSERT INTO public.role_permissions VALUES (3, 1, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (3, 2, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (3, 3, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (3, 4, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (3, 5, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (3, 6, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (3, 7, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (3, 8, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (3, 9, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (3, 10, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (3, 11, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (3, 12, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (3, 13, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (3, 14, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (3, 15, '2026-11-27 05:57:44.879334');
INSERT INTO public.role_permissions VALUES (2, 1, '2026-11-27 05:57:44.8847');
INSERT INTO public.role_permissions VALUES (2, 2, '2026-11-27 05:57:44.8847');
INSERT INTO public.role_permissions VALUES (2, 3, '2026-11-27 05:57:44.8847');
INSERT INTO public.role_permissions VALUES (2, 5, '2026-11-27 05:57:44.8847');
INSERT INTO public.role_permissions VALUES (2, 6, '2026-11-27 05:57:44.8847');
INSERT INTO public.role_permissions VALUES (2, 7, '2026-11-27 05:57:44.8847');
INSERT INTO public.role_permissions VALUES (2, 9, '2026-11-27 05:57:44.8847');
INSERT INTO public.role_permissions VALUES (2, 10, '2026-11-27 05:57:44.8847');
INSERT INTO public.role_permissions VALUES (2, 11, '2026-11-27 05:57:44.8847');
INSERT INTO public.role_permissions VALUES (2, 12, '2026-11-27 05:57:44.8847');
INSERT INTO public.role_permissions VALUES (2, 13, '2026-11-27 05:57:44.8847');
INSERT INTO public.role_permissions VALUES (2, 15, '2026-11-27 05:57:44.8847');
INSERT INTO public.role_permissions VALUES (1, 1, '2026-11-27 05:57:44.887595');
























SELECT pg_catalog.setval('public.bulk_enrollment_logs_id_seq', 1, false);



SELECT pg_catalog.setval('public.competency_frameworks_id_seq', 1, false);



SELECT pg_catalog.setval('public.content_progress_id_seq', 1, false);



SELECT pg_catalog.setval('public.content_skills_id_seq', 1, false);



SELECT pg_catalog.setval('public.course_co_teachers_id_seq', 1, false);



SELECT pg_catalog.setval('public.course_competencies_id_seq', 1, false);



SELECT pg_catalog.setval('public.course_sections_id_seq', 1, false);



SELECT pg_catalog.setval('public.courses_id_seq', 1, false);



SELECT pg_catalog.setval('public.enrollments_id_seq', 1, false);



SELECT pg_catalog.setval('public.forum_comments_id_seq', 1, false);



SELECT pg_catalog.setval('public.forum_posts_id_seq', 1, false);



SELECT pg_catalog.setval('public.forum_votes_id_seq', 1, false);



SELECT pg_catalog.setval('public.learner_skill_states_id_seq', 1, false);



SELECT pg_catalog.setval('public.learning_events_id_seq', 1, false);



SELECT pg_catalog.setval('public.learning_notification_events_id_seq', 1, false);



SELECT pg_catalog.setval('public.micro_lesson_interactions_id_seq', 1, false);



SELECT pg_catalog.setval('public.micro_lesson_jobs_id_seq', 1, false);



SELECT pg_catalog.setval('public.micro_lessons_id_seq', 1, false);



SELECT pg_catalog.setval('public.micro_quiz_jobs_id_seq', 1, false);



SELECT pg_catalog.setval('public.micro_quizzes_id_seq', 1, false);



SELECT pg_catalog.setval('public.organization_members_id_seq', 1, false);



SELECT pg_catalog.setval('public.organizations_id_seq', 1, true);



SELECT pg_catalog.setval('public.permissions_id_seq', 15, true);



SELECT pg_catalog.setval('public.question_bank_items_id_seq', 1, false);



SELECT pg_catalog.setval('public.question_skills_id_seq', 1, false);



SELECT pg_catalog.setval('public.quiz_analytics_id_seq', 1, false);



SELECT pg_catalog.setval('public.quiz_answer_options_id_seq', 1, false);



SELECT pg_catalog.setval('public.quiz_attempts_id_seq', 1, false);



SELECT pg_catalog.setval('public.quiz_correct_answers_id_seq', 1, false);



SELECT pg_catalog.setval('public.quiz_questions_id_seq', 1, false);



SELECT pg_catalog.setval('public.quiz_student_answers_id_seq', 1, false);



SELECT pg_catalog.setval('public.quizzes_id_seq', 1, false);



SELECT pg_catalog.setval('public.role_definitions_id_seq', 3, true);



SELECT pg_catalog.setval('public.section_content_id_seq', 1, false);



SELECT pg_catalog.setval('public.section_overview_jobs_id_seq', 1, false);



SELECT pg_catalog.setval('public.section_overview_lessons_id_seq', 1, false);



SELECT pg_catalog.setval('public.section_overview_quizzes_id_seq', 1, false);



SELECT pg_catalog.setval('public.skill_prerequisites_id_seq', 1, false);



SELECT pg_catalog.setval('public.skill_recommendations_id_seq', 1, false);



SELECT pg_catalog.setval('public.skill_relationships_id_seq', 1, false);



SELECT pg_catalog.setval('public.skills_id_seq', 1, false);



SELECT pg_catalog.setval('public.user_roles_id_seq', 1, false);



SELECT pg_catalog.setval('public.users_id_seq', 1, false);
