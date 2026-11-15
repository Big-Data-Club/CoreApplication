package repository

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
)

type DBTX interface {
	ExecContext(context.Context, string, ...interface{}) (sql.Result, error)
	QueryContext(context.Context, string, ...interface{}) (*sql.Rows, error)
	QueryRowContext(context.Context, string, ...interface{}) *sql.Row
}

var ErrCallbackScope = errors.New("callback does not match its job")
var ErrCallbackConflict = errors.New("callback result already saved with different payload")

// saveCallback commits all generated records and the dedupe receipt together.
// One row per job serializes concurrent retries without duplicating generated items.
func saveCallback(ctx context.Context, db DBTX, kind string, jobID int64, body interface{}, save func(DBTX) error) error {
	starter, ok := db.(interface {
		BeginTx(context.Context, *sql.TxOptions) (*sql.Tx, error)
	})
	if !ok {
		return errors.New("callback requires transactional database")
	}
	encoded, err := json.Marshal(body)
	if err != nil {
		return err
	}
	digest := sha256.Sum256(encoded)
	hash := hex.EncodeToString(digest[:])
	tx, err := starter.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	result, err := tx.ExecContext(ctx, `INSERT INTO lms_callback_receipts(kind,job_id,payload_hash) VALUES($1,$2,$3) ON CONFLICT DO NOTHING`, kind, jobID, hash)
	if err != nil {
		return err
	}
	n, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		var previous string
		if err := tx.QueryRowContext(ctx, `SELECT payload_hash FROM lms_callback_receipts WHERE kind=$1 AND job_id=$2`, kind, jobID).Scan(&previous); err != nil {
			return err
		}
		if previous != hash {
			return ErrCallbackConflict
		}
		return tx.Commit()
	}
	if err := save(tx); err != nil {
		return err
	}
	return tx.Commit()
}
