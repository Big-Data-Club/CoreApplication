-- V018: Sync existing quiz questions into the question bank.
--
-- 1. Extends the provenance enum with 'QUIZ' (synced from an existing quiz).
-- 2. One-time backfill of EVERY existing quiz question into the bank,
--    keeping node/bloom/points and copying answer options + correct answers
--    into the same JSONB contracts the bank stores.
-- 3. De-duplicates the bank by (course_id, normalized text) then locks it in
--    with a unique expression index so re-runs and future syncs are idempotent.

-- ── 1. Source enum += 'QUIZ' ────────────────────────────────────────────────
ALTER TABLE question_bank_items
    DROP CONSTRAINT IF EXISTS question_bank_items_source_check;
ALTER TABLE question_bank_items
    ADD CONSTRAINT question_bank_items_source_check CHECK (source IN
        ('MANUAL','IMPORT','AI_GENERATED','QUIZ'));

-- ── 2. Backfill from live quizzes ───────────────────────────────────────────
INSERT INTO question_bank_items (
    course_id, node_id, source_quiz_id, question_type, question_text,
    explanation, points, bloom_level, difficulty,
    answer_options, correct_answers, settings, tags,
    source, status, created_by
)
SELECT
    cs.course_id,
    qq.node_id,
    qz.id,
    qq.question_type,
    qq.question_text,
    qq.explanation,
    COALESCE(qq.points, 10),
    qq.bloom_level,
    'MEDIUM',
    COALESCE(opts.jsonb, '[]'::jsonb),
    COALESCE(cans.jsonb, '[]'::jsonb),
    COALESCE(qq.settings, '{}'::jsonb),
    '{}'::text[],
    'QUIZ',
    'APPROVED',
    qz.created_by
FROM quiz_questions qq
JOIN quizzes         qz ON qz.id = qq.quiz_id
JOIN section_content sc ON sc.id = qz.content_id
JOIN course_sections cs ON cs.id = sc.section_id
LEFT JOIN LATERAL (
    SELECT jsonb_agg(
               json_build_object(
                   'option_text', o.option_text,
                   'is_correct',  COALESCE(o.is_correct, false),
                   'order_index', o.order_index,
                   'blank_id',    o.blank_id
               ) ORDER BY o.order_index
           ) AS jsonb
    FROM quiz_answer_options o
    WHERE o.question_id = qq.id
) opts ON true
LEFT JOIN LATERAL (
    SELECT jsonb_agg(
               json_build_object(
                   'answer_text',    a.answer_text,
                   'blank_id',       a.blank_id,
                   'blank_position', a.blank_position,
                   'case_sensitive', COALESCE(a.case_sensitive, false),
                   'exact_match',    COALESCE(a.exact_match, true)
               )
           ) AS jsonb
    FROM quiz_correct_answers a
    WHERE a.question_id = qq.id
) cans ON true
WHERE NOT EXISTS (
    SELECT 1
    FROM question_bank_items bi
    WHERE bi.course_id = cs.course_id
      AND md5(btrim(bi.question_text)) = md5(btrim(qq.question_text))
);

-- ── 3. Enforce uniqueness going forward ─────────────────────────────────────
-- Normalisation scope = whitespace-trim ONLY (btrim): re-running this
-- migration and repeated quiz->bank syncs of the same question are no-ops,
-- while genuinely different wordings stay distinct. Fuzzy dedup is handled
-- upstream (AI generation uses token-Jaccard against existing texts).
DELETE FROM question_bank_items a
USING question_bank_items b
WHERE a.course_id = b.course_id
  AND a.id > b.id
  AND md5(btrim(a.question_text)) = md5(btrim(b.question_text));

CREATE UNIQUE INDEX IF NOT EXISTS uq_qbank_course_qtext
    ON question_bank_items (course_id, md5(btrim(question_text)));
