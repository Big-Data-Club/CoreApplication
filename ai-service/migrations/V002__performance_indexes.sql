-- =============================================================================
-- V002__performance_indexes.sql
-- =============================================================================

-- ── knowledge_nodes ───────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_kn_course  ON knowledge_nodes(course_id);
CREATE INDEX IF NOT EXISTS idx_kn_parent  ON knowledge_nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_kn_level   ON knowledge_nodes(course_id, level);
CREATE INDEX IF NOT EXISTS idx_kn_source  ON knowledge_nodes(source_content_id)
    WHERE source_content_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_kn_source_content
    ON knowledge_nodes (source_content_id, source_content_title)
    WHERE source_content_id IS NOT NULL;

-- ── knowledge_node_relations ──────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_knr_source ON knowledge_node_relations(source_node_id);
CREATE INDEX IF NOT EXISTS idx_knr_target ON knowledge_node_relations(target_node_id);
CREATE INDEX IF NOT EXISTS idx_knr_course ON knowledge_node_relations(course_id);

-- ── document_chunks ──────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_dc_content ON document_chunks(content_id);
CREATE INDEX IF NOT EXISTS idx_dc_node    ON document_chunks(node_id);
CREATE INDEX IF NOT EXISTS idx_dc_course  ON document_chunks(course_id);
CREATE INDEX IF NOT EXISTS idx_dc_status  ON document_chunks(status);
CREATE INDEX IF NOT EXISTS idx_dc_hash    ON document_chunks(chunk_hash);
CREATE INDEX IF NOT EXISTS idx_dc_content_status
    ON document_chunks (content_id, status);
CREATE INDEX IF NOT EXISTS idx_dc_node_status
    ON document_chunks (node_id, status)
    WHERE node_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dc_parent ON document_chunks(parent_chunk_id);
CREATE INDEX IF NOT EXISTS idx_dc_level  ON document_chunks(chunk_level);

-- ── ai_diagnoses ──────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_ad_student  ON ai_diagnoses(student_id);
CREATE INDEX IF NOT EXISTS idx_ad_question ON ai_diagnoses(question_id);
CREATE INDEX IF NOT EXISTS idx_ad_node     ON ai_diagnoses(node_id);
CREATE INDEX IF NOT EXISTS idx_ad_cache_lookup
    ON ai_diagnoses (question_id, md5(wrong_answer))
    WHERE question_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ad_student_node
    ON ai_diagnoses (student_id, node_id, created_at DESC)
    WHERE node_id IS NOT NULL;

-- ── content_index_status ─────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_cis_course ON content_index_status(course_id);
CREATE INDEX IF NOT EXISTS idx_cis_status ON content_index_status(status);
CREATE INDEX IF NOT EXISTS idx_cis_course_status
    ON content_index_status (course_id, status);

-- ── student_knowledge_progress ───────────────────────────────
CREATE INDEX IF NOT EXISTS idx_skp_student_course ON student_knowledge_progress(student_id, course_id);
CREATE INDEX IF NOT EXISTS idx_skp_node           ON student_knowledge_progress(node_id);
CREATE INDEX IF NOT EXISTS idx_skp_mastery        ON student_knowledge_progress(mastery_level);
CREATE INDEX IF NOT EXISTS idx_skp_node_course
    ON student_knowledge_progress (node_id, course_id);

-- ── spaced_repetitions ────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sr_due    ON spaced_repetitions(student_id, next_review_date);
CREATE INDEX IF NOT EXISTS idx_sr_course ON spaced_repetitions(student_id, course_id);
CREATE INDEX IF NOT EXISTS idx_sr_student_due_today
    ON spaced_repetitions (student_id, course_id, next_review_date)
    INCLUDE (question_id, easiness_factor, interval_days, repetitions)
    WHERE next_review_date <= CURRENT_DATE;
CREATE INDEX IF NOT EXISTS idx_sr_course_date
    ON spaced_repetitions (student_id, course_id, next_review_date);

-- ── ai_quiz_generations ───────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_aiqg_node   ON ai_quiz_generations(node_id);
CREATE INDEX IF NOT EXISTS idx_aiqg_status ON ai_quiz_generations(status);
CREATE INDEX IF NOT EXISTS idx_aiqg_course ON ai_quiz_generations(course_id);
CREATE INDEX IF NOT EXISTS idx_aiqg_course_status_node
    ON ai_quiz_generations (course_id, status, node_id);

-- ── flashcards ────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_fc_student_node ON flashcards(student_id, node_id);
CREATE INDEX IF NOT EXISTS idx_fc_course       ON flashcards(course_id);
CREATE INDEX IF NOT EXISTS idx_fc_student_course_node
    ON flashcards (student_id, course_id, node_id)
    WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_fc_lesson ON flashcards(lesson_id);
CREATE INDEX IF NOT EXISTS idx_flashcards_content_id ON flashcards(content_id);

-- ── flashcard_repetitions ─────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_fcr_due ON flashcard_repetitions(student_id, course_id, next_review_date);
CREATE INDEX IF NOT EXISTS idx_fcr_student_due_today
    ON flashcard_repetitions (student_id, course_id, next_review_date)
    INCLUDE (flashcard_id, easiness_factor, interval_days, repetitions)
    WHERE next_review_date <= CURRENT_DATE;

-- ── embedding_reindex_jobs ────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_erj_status  ON embedding_reindex_jobs(status);
CREATE INDEX IF NOT EXISTS idx_erj_course  ON embedding_reindex_jobs(course_id);
CREATE INDEX IF NOT EXISTS idx_erj_content ON embedding_reindex_jobs(content_id);

-- ── agent_sessions ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_as_user ON agent_sessions(user_id, agent_type);
CREATE INDEX IF NOT EXISTS idx_as_active ON agent_sessions(last_active_at);
CREATE INDEX IF NOT EXISTS idx_as_course ON agent_sessions(course_id) WHERE course_id IS NOT NULL;

-- ── agent_episodes ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_ae_user ON agent_episodes(user_id, agent_type);
CREATE INDEX IF NOT EXISTS idx_ae_session ON agent_episodes(session_id);
CREATE INDEX IF NOT EXISTS idx_ae_user_course ON agent_episodes(user_id, agent_type, course_id) WHERE course_id IS NOT NULL;

-- ── agent_messages ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_am_session ON agent_messages(session_id, created_at);

-- ── llm_api_keys ──────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_llm_api_keys_pool
    ON llm_api_keys (provider_id, status, cooldown_until);

-- ── llm_models ────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_llm_models_provider ON llm_models (provider_id, enabled);

-- ── task_model_bindings ───────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_task_bindings_chain
    ON task_model_bindings (task_code, enabled, priority);

-- ── llm_usage_log ─────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_usage_log_created ON llm_usage_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_log_task    ON llm_usage_log (task_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_log_model   ON llm_usage_log (model_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_log_key     ON llm_usage_log (api_key_id, created_at DESC);

-- ── graph_consolidation_log ───────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_gcl_course   ON graph_consolidation_log(course_id);
CREATE INDEX IF NOT EXISTS idx_gcl_survivor ON graph_consolidation_log(survivor_id);
CREATE INDEX IF NOT EXISTS idx_gcl_created  ON graph_consolidation_log(created_at DESC);

-- ── Analyze updated tables so planner picks up new indexes immediately ────────
ANALYZE ai_diagnoses;
ANALYZE spaced_repetitions;
ANALYZE flashcard_repetitions;
ANALYZE document_chunks;
ANALYZE knowledge_nodes;
ANALYZE ai_quiz_generations;
ANALYZE student_knowledge_progress;
ANALYZE content_index_status;
ANALYZE flashcards;
ANALYZE agent_sessions;
ANALYZE agent_episodes;
ANALYZE agent_messages;
ANALYZE llm_providers;
ANALYZE llm_api_keys;
ANALYZE llm_models;
ANALYZE task_model_bindings;
ANALYZE llm_usage_log;
ANALYZE graph_consolidation_log;
