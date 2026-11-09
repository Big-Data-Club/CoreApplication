package database

import (
	"context"
	"database/sql"
	"fmt"

	"example/hello/migrations"
)

func EnsureLearningNotificationSchema(ctx context.Context, db *sql.DB) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err = tx.ExecContext(ctx, `SET LOCAL lock_timeout = '5s'`); err != nil {
		return err
	}
	if _, err = tx.ExecContext(ctx, `SELECT pg_advisory_xact_lock(2026110901)`); err != nil {
		return err
	}
	var ready bool
	err = tx.QueryRowContext(ctx, `SELECT to_regclass('learning_notification_events') IS NOT NULL
 AND to_regclass('learning_notification_reads') IS NOT NULL
 AND to_regprocedure('lms_notification_scope(bigint)') IS NOT NULL
 AND to_regprocedure('capture_learning_notification()') IS NOT NULL
 AND (SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname IN('capture_course_notification','capture_section_notification','capture_content_notification'))=3`).Scan(&ready)
	if err != nil {
		return err
	}
	if !ready {
		if _, err = tx.ExecContext(ctx, migrations.LearningNotifications); err != nil {
			return fmt.Errorf("install learning notification schema (V021): %w", err)
		}
	}
	return tx.Commit()
}
