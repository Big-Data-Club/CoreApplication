-- One durable change record per mutation, no recipient fan-out or catalog scan.
-- The transaction's trigger is the outbox producer; Redis is only a wake-up hint.
CREATE TABLE learning_notification_events (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL,
    section_id BIGINT,
    content_id BIGINT,
    kind TEXT NOT NULL,
    entity_title TEXT NOT NULL,
    group_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ
);
CREATE INDEX idx_learning_notifications_course ON learning_notification_events(course_id, created_at DESC);
CREATE INDEX idx_learning_notifications_pending ON learning_notification_events(id) WHERE delivered_at IS NULL;
CREATE INDEX idx_learning_notifications_created ON learning_notification_events(created_at);
CREATE TABLE learning_notification_reads (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notification_key VARCHAR(160) NOT NULL,
    read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(user_id, notification_key)
);
CREATE INDEX idx_learning_notification_reads_time ON learning_notification_reads(user_id, read_at DESC);
CREATE INDEX idx_learning_notification_reads_expiry ON learning_notification_reads(read_at);

-- Match the catalog's membership + private-organization boundary at read time.
CREATE FUNCTION lms_notification_scope(viewer BIGINT)
RETURNS TABLE(course_id BIGINT, title VARCHAR, org_id BIGINT, visibility VARCHAR, enrolled BOOLEAN)
LANGUAGE sql STABLE AS $$
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

CREATE FUNCTION capture_learning_notification() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE TRIGGER capture_course_notification AFTER INSERT OR UPDATE ON courses
    FOR EACH ROW EXECUTE FUNCTION capture_learning_notification();
CREATE TRIGGER capture_section_notification AFTER INSERT OR UPDATE OR DELETE ON course_sections
    FOR EACH ROW EXECUTE FUNCTION capture_learning_notification();
CREATE TRIGGER capture_content_notification AFTER INSERT OR UPDATE OR DELETE ON section_content
    FOR EACH ROW EXECUTE FUNCTION capture_learning_notification();

-- Only known publication times can be backfilled; never invent past edits.
INSERT INTO learning_notification_events(course_id, kind, entity_title, group_key, created_at, delivered_at)
SELECT id, 'course_published', title, 'course_published:' || id, published_at, now()
FROM courses WHERE status = 'PUBLISHED' AND published_at >= now() - interval '14 days';
