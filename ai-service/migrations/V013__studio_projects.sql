-- V013: Content Studio projects.
-- One row = one teacher authoring effort (slides / document / video later).
-- The plan is teacher-editable BEFORE generation; artifacts are stored on
-- MinIO and referenced by URL. Section-level hashes enable partial re-render.

CREATE TABLE IF NOT EXISTS studio_projects (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id    BIGINT NOT NULL,
    created_by   BIGINT NOT NULL,
    kind         VARCHAR(20) NOT NULL CHECK (kind IN ('slides','document','video')),
    title        VARCHAR(300) NOT NULL,

    status       VARCHAR(20) NOT NULL DEFAULT 'collecting'
                 CHECK (status IN ('collecting','planned','generating','ready','failed')),
    error_detail TEXT,

    context_pack JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{type,ref,title,text}]
    plan         JSONB,                                -- teacher-approved StudioPlan
    settings     JSONB NOT NULL DEFAULT '{}'::jsonb,   -- theme, slide_count, language...

    artifacts    JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{type,url,section_hashes}]
    section_hashes JSONB NOT NULL DEFAULT '{}'::jsonb, -- {idx: md5(section payload)}

    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_studio_course
    ON studio_projects(course_id, created_at DESC);
