-- Deliberately separate from document_chunks and the public course RAG corpus.
CREATE TABLE IF NOT EXISTS quiz_index_jobs (
    quiz_id BIGINT PRIMARY KEY,
    course_id BIGINT NOT NULL,
    requester_id BIGINT NOT NULL,
    job_id UUID NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('pending','processing','ready','failed')),
    revision TEXT NOT NULL,
    generation UUID,
    processed INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    lease_until TIMESTAMPTZ,
    claim_id UUID,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS quiz_question_chunks (
    quiz_id BIGINT NOT NULL,
    generation UUID NOT NULL,
    question_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    source_hash TEXT NOT NULL,
    content TEXT NOT NULL,
    node_id BIGINT REFERENCES knowledge_nodes(id) ON DELETE SET NULL,
    suggested_node_id BIGINT REFERENCES knowledge_nodes(id) ON DELETE SET NULL,
    suggestion_score DOUBLE PRECISION,
    PRIMARY KEY (quiz_id,generation,question_id)
);
CREATE INDEX IF NOT EXISTS quiz_chunks_course_node ON quiz_question_chunks(course_id,node_id);
CREATE TABLE IF NOT EXISTS quiz_node_approvals (
 quiz_id BIGINT NOT NULL, question_id BIGINT NOT NULL, source_hash TEXT NOT NULL,
 node_id BIGINT NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
 PRIMARY KEY(quiz_id,question_id,source_hash)
);
