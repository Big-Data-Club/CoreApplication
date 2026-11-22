-- Bounded course-list queries sort by their display timestamps after applying
-- ownership/visibility filters. These indexes avoid sorting the full course
-- table before LIMIT can be applied.
CREATE INDEX IF NOT EXISTS idx_courses_creator_created_page
    ON courses(created_by, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_courses_published_page
    ON courses(published_at DESC, id DESC)
    WHERE status = 'PUBLISHED';

CREATE INDEX IF NOT EXISTS idx_courses_org_published_page
    ON courses(org_id, published_at DESC, id DESC)
    WHERE status = 'PUBLISHED';

ANALYZE courses;
