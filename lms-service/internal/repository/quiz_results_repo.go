package repository

import (
	"context"
	"encoding/json"
	"example/hello/internal/dto"
)

// GetQuizResults reads one snapshot, aggregates answers once, and bounds both
// learner and attempt rows. Score metrics always cover the entire quiz.
func (r *QuizRepository) GetQuizResults(ctx context.Context, quizID int64, options ...dto.QuizResultsQuery) (json.RawMessage, error) {
	query := dto.QuizResultsQuery{AttemptPage: 1, StudentPage: 1}
	if len(options) > 0 {
		query = options[0]
	}
	if query.AttemptPage < 1 {
		query.AttemptPage = 1
	}
	if query.StudentPage < 1 {
		query.StudentPage = 1
	}
	var report []byte
	err := r.db.QueryRowContext(ctx, `
 WITH base AS MATERIALIZED (
 SELECT a.id,a.student_id,COALESCE(u.full_name,'') AS student_name,a.attempt_number,
 a.started_at,a.submitted_at,a.status,a.percentage,a.total_points,a.earned_points,
 a.is_passed,a.time_spent_seconds,a.focus_summary
 FROM quiz_attempts a LEFT JOIN users u ON u.id=a.student_id WHERE a.quiz_id=$1
 ), answers AS MATERIALIZED (
 SELECT s.attempt_id,s.question_id,s.points_earned,s.is_correct,s.time_spent_seconds,
 s.answer_data->'selected_option_id' AS selected_option_id,
 s.answer_data->'selected_option_ids' AS selected_option_ids
 FROM quiz_student_answers s JOIN base a ON a.id=s.attempt_id WHERE a.submitted_at IS NOT NULL
 ), pending AS (
 SELECT attempt_id,COUNT(*) FILTER(WHERE points_earned IS NULL) AS count FROM answers GROUP BY attempt_id
 ), attempts AS MATERIALIZED (
 SELECT a.*,COALESCE(p.count,0) AS pending_answers FROM base a LEFT JOIN pending p ON p.attempt_id=a.id
 ), scored AS MATERIALIZED (
 SELECT * FROM attempts WHERE submitted_at IS NOT NULL AND percentage IS NOT NULL AND pending_answers=0
 ), matched AS MATERIALIZED (
 SELECT * FROM attempts WHERE $2='' OR strpos(lower(student_name),lower($2))>0 OR strpos(student_id::text,$2)>0
 ), learner_stats AS (
 SELECT student_id,MAX(student_name) AS student_name,COUNT(*) AS total_attempts,
 COUNT(*) FILTER(WHERE submitted_at IS NOT NULL) AS submitted_attempts,
 MAX(percentage) FILTER(WHERE submitted_at IS NOT NULL AND pending_answers=0) AS best_percentage,
 AVG(percentage) FILTER(WHERE submitted_at IS NOT NULL AND pending_answers=0) AS average_percentage,
 MAX(id) AS latest_attempt_id
 FROM matched GROUP BY student_id
 ), learners AS (
 SELECT s.*,to_jsonb(a) AS latest_attempt FROM learner_stats s JOIN attempts a ON a.id=s.latest_attempt_id
 ), selected_options AS (
 SELECT question_id,option_id,COUNT(DISTINCT attempt_id) AS count FROM (
 SELECT s.attempt_id,s.question_id,s.selected_option_id #>> '{}' AS option_id FROM answers s WHERE s.selected_option_id #>> '{}' IS NOT NULL
 UNION ALL
 SELECT s.attempt_id,s.question_id,v.option_id FROM answers s CROSS JOIN LATERAL jsonb_array_elements_text(
 CASE WHEN jsonb_typeof(s.selected_option_ids)='array' THEN s.selected_option_ids ELSE '[]'::jsonb END) v(option_id)
 ) selections GROUP BY question_id,option_id
 ), question_stats AS (
 SELECT question_id,COUNT(*) AS answered,COUNT(*) FILTER(WHERE is_correct=true) AS correct,
 COUNT(*) FILTER(WHERE is_correct=false) AS incorrect,COUNT(*) FILTER(WHERE points_earned IS NULL) AS pending,
 AVG(points_earned) AS average_points,AVG(time_spent_seconds) AS average_seconds
 FROM answers GROUP BY question_id
 ), options AS (
 SELECT o.question_id,jsonb_agg(jsonb_build_object('id',o.id,'option_text',o.option_text,
 'is_correct',o.is_correct,'selected_count',COALESCE(s.count,0)) ORDER BY o.order_index,o.id) AS items
 FROM quiz_answer_options o JOIN quiz_questions q ON q.id=o.question_id AND q.quiz_id=$1
 LEFT JOIN selected_options s ON s.question_id=o.question_id AND s.option_id=o.id::text GROUP BY o.question_id
 ), correct_answers AS (
 SELECT c.question_id,jsonb_agg(jsonb_build_object('answer_text',c.answer_text,'blank_id',c.blank_id) ORDER BY c.id) AS items
 FROM quiz_correct_answers c JOIN quiz_questions q ON q.id=c.question_id AND q.quiz_id=$1 GROUP BY c.question_id
 ), questions AS (
 SELECT q.id,q.question_text,q.question_type,q.points,q.order_index,
 COALESCE(o.items,'[]'::jsonb) AS answer_options,COALESCE(c.items,'[]'::jsonb) AS correct_answers,
 COALESCE(s.answered,0) AS answered,COALESCE(s.correct,0) AS correct,COALESCE(s.incorrect,0) AS incorrect,
 COALESCE(s.pending,0) AS pending,s.average_points,s.average_seconds
 FROM quiz_questions q LEFT JOIN question_stats s ON s.question_id=q.id
 LEFT JOIN options o ON o.question_id=q.id LEFT JOIN correct_answers c ON c.question_id=q.id WHERE q.quiz_id=$1
 ), summary AS (
 SELECT COUNT(*) AS total_attempts,COUNT(DISTINCT student_id) AS unique_students,
 COUNT(*) FILTER(WHERE submitted_at IS NOT NULL) AS submitted_attempts,
 COUNT(*) FILTER(WHERE submitted_at IS NOT NULL AND pending_answers>0) AS pending_attempts,
 COALESCE(SUM(pending_answers),0) AS pending_answers,
 (SELECT COUNT(*) FROM scored) AS graded_attempts,
 (SELECT AVG(percentage) FROM scored) AS average_percentage,
 (SELECT MIN(percentage) FROM scored) AS minimum_percentage,
 (SELECT MAX(percentage) FROM scored) AS maximum_percentage,
 (SELECT percentile_cont(0.5) WITHIN GROUP(ORDER BY percentage) FROM scored) AS median_percentage,
 (SELECT 100.0*COUNT(*) FILTER(WHERE is_passed=true)/NULLIF(COUNT(is_passed),0) FROM scored) AS pass_rate,
 COUNT(*) FILTER(WHERE submitted_at IS NOT NULL AND focus_summary IS NOT NULL) AS focus_available_attempts,
 COALESCE(SUM((focus_summary->>'departures')::bigint) FILTER(WHERE submitted_at IS NOT NULL),0) AS total_departures,
 COALESCE(SUM((focus_summary->>'away_seconds')::bigint) FILTER(WHERE submitted_at IS NOT NULL),0) AS total_away_seconds,
 AVG(time_spent_seconds) FILTER(WHERE submitted_at IS NOT NULL) AS average_seconds
 FROM attempts
 ), distribution AS (
 SELECT bucket,COUNT(s.id) AS count FROM generate_series(0,4) bucket LEFT JOIN scored s
 ON s.percentage>=bucket*20 AND (s.percentage<(bucket+1)*20 OR bucket=4 AND s.percentage<=100) GROUP BY bucket
 )
 SELECT jsonb_build_object('quiz_id',$1::bigint,'title',(SELECT title FROM quizzes WHERE id=$1),
 'summary',(SELECT to_jsonb(s) FROM summary s),
 'distribution',COALESCE((SELECT jsonb_agg(to_jsonb(d) ORDER BY bucket) FROM distribution d),'[]'::jsonb),
 'attempts',COALESCE((SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id DESC) FROM (SELECT * FROM matched ORDER BY id DESC LIMIT 50 OFFSET $3) a),'[]'::jsonb),
 'students',COALESCE((SELECT jsonb_agg(to_jsonb(s) ORDER BY s.student_id) FROM (SELECT * FROM learners ORDER BY student_id LIMIT 50 OFFSET $4) s),'[]'::jsonb),
 'attempts_total',(SELECT COUNT(*) FROM matched),'students_total',(SELECT COUNT(*) FROM learner_stats),
 'attempt_page',$5::int,'student_page',$6::int,'page_size',50,
 'questions',COALESCE((SELECT jsonb_agg(to_jsonb(q) ORDER BY q.order_index,q.id) FROM questions q),'[]'::jsonb))`,
		quizID, query.Search, (query.AttemptPage-1)*50, (query.StudentPage-1)*50, query.AttemptPage, query.StudentPage).Scan(&report)
	return json.RawMessage(report), err
}

// GetQuizResultRows fetches only visible rows. It does not recompute question
// statistics or scan answers outside the selected attempts/50 learners.
func (r *QuizRepository) GetQuizResultRows(ctx context.Context, quizID int64, q dto.QuizResultsQuery) (json.RawMessage, error) {
	var result []byte
	err := r.db.QueryRowContext(ctx, `
 WITH matched AS MATERIALIZED (
 SELECT a.id,a.student_id,COALESCE(u.full_name,'') AS student_name
 FROM quiz_attempts a LEFT JOIN users u ON u.id=a.student_id
 WHERE a.quiz_id=$1 AND ($2='' OR strpos(lower(COALESCE(u.full_name,'')),lower($2))>0 OR strpos(a.student_id::text,$2)>0)
 ), page_students AS (
 SELECT DISTINCT student_id FROM matched ORDER BY student_id LIMIT 50 OFFSET $4
 ), page_attempts AS (
 SELECT id FROM matched ORDER BY id DESC LIMIT 50 OFFSET $3
 ), selected AS MATERIALIZED (
 SELECT a.id,a.student_id,COALESCE(u.full_name,'') AS student_name,a.attempt_number,
 a.started_at,a.submitted_at,a.status,a.percentage,a.total_points,a.earned_points,
 a.is_passed,a.time_spent_seconds,a.focus_summary,
 (SELECT COUNT(*) FROM quiz_student_answers s WHERE s.attempt_id=a.id AND s.points_earned IS NULL AND a.submitted_at IS NOT NULL) AS pending_answers
 FROM quiz_attempts a LEFT JOIN users u ON u.id=a.student_id WHERE a.quiz_id=$1
 AND (a.id IN(SELECT id FROM page_attempts) OR a.student_id IN(SELECT student_id FROM page_students))
 ), learner_stats AS (
 SELECT student_id,MAX(student_name) AS student_name,COUNT(*) AS total_attempts,
 COUNT(*) FILTER(WHERE submitted_at IS NOT NULL) AS submitted_attempts,
 MAX(percentage) FILTER(WHERE submitted_at IS NOT NULL AND pending_answers=0) AS best_percentage,
 AVG(percentage) FILTER(WHERE submitted_at IS NOT NULL AND pending_answers=0) AS average_percentage,
 MAX(id) AS latest_attempt_id FROM selected WHERE student_id IN(SELECT student_id FROM page_students) GROUP BY student_id
 ), learners AS (
 SELECT s.*,to_jsonb(a) AS latest_attempt FROM learner_stats s JOIN selected a ON a.id=s.latest_attempt_id
 )
 SELECT jsonb_build_object(
 'attempts',COALESCE((SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id DESC) FROM selected a WHERE a.id IN(SELECT id FROM page_attempts)),'[]'::jsonb),
 'students',COALESCE((SELECT jsonb_agg(to_jsonb(s) ORDER BY s.student_id) FROM learners s),'[]'::jsonb),
 'attempts_total',(SELECT COUNT(*) FROM matched),'students_total',(SELECT COUNT(DISTINCT student_id) FROM matched),
 'attempt_page',$5::int,'student_page',$6::int,'page_size',50)`, quizID, q.Search, (q.AttemptPage-1)*50, (q.StudentPage-1)*50, q.AttemptPage, q.StudentPage).Scan(&result)
	return json.RawMessage(result), err
}
