package database

import (
	"context"
	"database/sql"
	_ "embed"
)

//go:embed farm_learning_schema.sql
var farmLearningSchema string

// EnsureFarmLearningSchema applies the additive V019 migration during rollout.
// A transaction advisory lock serializes concurrent LMS replicas.
func EnsureFarmLearningSchema(ctx context.Context, db *sql.DB) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err = tx.ExecContext(ctx, "SELECT pg_advisory_xact_lock(734620119)"); err != nil {
		return err
	}
	if _, err = tx.ExecContext(ctx, farmLearningSchema); err != nil {
		return err
	}
	return tx.Commit()
}
