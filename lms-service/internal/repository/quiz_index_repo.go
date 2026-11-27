package repository

import (
	"context"
	"encoding/json"
	"fmt"
)

// The fingerprint includes every indexed field and option, never answer keys.
// Trigger-maintained revision/count make head checks O(1); pages are bounded.
const quizIndexSource = `SELECT q.id,q.node_id,q.question_text,q.points,
 COALESCE((SELECT jsonb_agg(o.option_text ORDER BY o.order_index,o.id)
 FROM quiz_answer_options o WHERE o.question_id=q.id),'[]'::jsonb) AS options
 FROM quiz_questions q WHERE q.quiz_id=$1`

func (r *QuizRepository) QuizIndexSource(ctx context.Context, quizID, after int64, head bool) (json.RawMessage, error) {
	var raw []byte
	if head {
		err := r.db.QueryRowContext(ctx, `SELECT jsonb_build_object('revision',md5(COALESCE(v.revision,0)::text),
   'total',COALESCE(v.question_count,0)) FROM quizzes q
   LEFT JOIN quiz_index_versions v ON v.quiz_id=q.id WHERE q.id=$1`, quizID).Scan(&raw)
		return raw, err
	}
	err := r.db.QueryRowContext(ctx, `WITH source AS (`+quizIndexSource+` AND q.id>$2 ORDER BY q.id LIMIT 100)
 SELECT COALESCE(jsonb_agg(to_jsonb(s)||jsonb_build_object('source_hash',md5(to_jsonb(s)::text)) ORDER BY id),'[]'::jsonb) FROM source s`, quizID, after).Scan(&raw)
	return raw, err
}

func (r *QuizRepository) SetQuizQuestionNode(ctx context.Context, quizID, questionID, nodeID int64, sourceHash string) error {
	// Lock the question AND its option rows against concurrent authoring. All source
	// comparisons are in the same transaction; callers must retry after an edit.
	tx, err := r.BeginTx(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	var id int64
	if err = tx.QueryRowContext(ctx, `SELECT id FROM quiz_questions WHERE quiz_id=$1 AND id=$2 FOR UPDATE`, quizID, questionID).Scan(&id); err != nil {
		return err
	}
	rows, err := tx.QueryContext(ctx, `SELECT id FROM quiz_answer_options WHERE question_id=$1 FOR UPDATE`, questionID)
	if err != nil {
		return err
	}
	for rows.Next() {
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return err
	}
	var current string
	err = tx.QueryRowContext(ctx, `WITH source AS (`+quizIndexSource+` AND q.id=$2) SELECT md5(to_jsonb(s)::text) FROM source s`, quizID, questionID).Scan(&current)
	if err != nil {
		return err
	}
	if current != sourceHash {
		return fmt.Errorf("question_changed")
	}
	if _, err = tx.ExecContext(ctx, `UPDATE quiz_questions SET node_id=$3,updated_at=now() WHERE quiz_id=$1 AND id=$2`, quizID, questionID, nodeID); err != nil {
		return err
	}
	return tx.Commit()
}
