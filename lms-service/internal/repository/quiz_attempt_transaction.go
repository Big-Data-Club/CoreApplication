package repository

import (
	"context"
	"database/sql"
	"fmt"
)

func beginTransaction(ctx context.Context, db DBTX) (*sql.Tx, error) {
	starter, ok := db.(interface {
		BeginTx(context.Context, *sql.TxOptions) (*sql.Tx, error)
	})
	if !ok {
		return nil, fmt.Errorf("nested transaction is not supported")
	}
	return starter.BeginTx(ctx, nil)
}

// WithAttemptLock keeps state checks, grading and answer writes in one transaction.
func (r *QuizRepository) WithAttemptLock(ctx context.Context, attemptID int64, fn func(*QuizRepository) error) error {
	tx, err := beginTransaction(ctx, r.db)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	var id int64
	if err := tx.QueryRowContext(ctx, `SELECT id FROM quiz_attempts WHERE id=$1 FOR UPDATE`, attemptID).Scan(&id); err != nil {
		return err
	}
	if err := fn(&QuizRepository{db: tx}); err != nil {
		return err
	}
	return tx.Commit()
}

// Starting/resuming is serialized per learner/quiz, not across all quiz takers.
func (r *QuizRepository) WithStartLock(ctx context.Context, quizID, userID int64, fn func(*QuizRepository) error) error {
	tx, err := beginTransaction(ctx, r.db)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err := tx.ExecContext(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1,0))`, fmt.Sprintf("quiz-start:%d:%d", quizID, userID)); err != nil {
		return err
	}
	if err := fn(&QuizRepository{db: tx}); err != nil {
		return err
	}
	return tx.Commit()
}
func (r *QuizRepository) EnqueueAttemptEffects(ctx context.Context, id int64) error {
	_, err := r.db.ExecContext(ctx, `INSERT INTO lms_quiz_effects(attempt_id) VALUES($1) ON CONFLICT DO NOTHING`, id)
	return err
}
func (r *QuizRepository) RefreshAttemptEffects(ctx context.Context, id int64) error {
	_, err := r.db.ExecContext(ctx, `INSERT INTO lms_quiz_effects(attempt_id) VALUES($1) ON CONFLICT(attempt_id) DO UPDATE SET local_completed_at=NULL,completed_at=NULL,available_at=now(),attempts=0`, id)
	return err
}
