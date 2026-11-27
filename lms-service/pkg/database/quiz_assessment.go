package database

import (
	"context"
	"database/sql"
	"example/hello/migrations"
)

// Existing/manual installations are detected before replay; concurrent replicas
// serialize the one-time backfill. Large databases should apply V024 pre-rollout.
func EnsureQuizAssessmentSchema(ctx context.Context, db *sql.DB) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err = tx.ExecContext(ctx, `SET LOCAL lock_timeout='5s'`); err != nil {
		return err
	}
	if _, err = tx.ExecContext(ctx, `SELECT pg_advisory_xact_lock(2026112701)`); err != nil {
		return err
	}
	var ready bool
	if err = tx.QueryRowContext(ctx, `SELECT to_regprocedure('capture_quiz_assessment_snapshot()') IS NOT NULL
 AND to_regclass('quiz_index_versions') IS NOT NULL
 AND (SELECT count(*) FROM pg_trigger WHERE tgname IN ('quiz_question_index_version','quiz_option_index_version') AND NOT tgisinternal AND tgenabled<>'D')=2
 AND EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='quiz_answer_assessment_snapshot'
 AND tgrelid='quiz_student_answers'::regclass AND tgenabled<>'D')`).Scan(&ready); err != nil {
		return err
	}
	if !ready {
		if _, err = tx.ExecContext(ctx, migrations.QuizAssessmentSnapshot); err != nil {
			return err
		}
	}
	return tx.Commit()
}
