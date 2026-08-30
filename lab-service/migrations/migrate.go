package migrations

import (
	"database/sql"
	"embed"
	"fmt"
	"sort"
)

//go:embed V*.sql
var files embed.FS

func Apply(db *sql.DB) error {
	if _, err := db.Exec(`CREATE TABLE IF NOT EXISTS lab_schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())`); err != nil {
		return err
	}
	entries, err := files.ReadDir(".")
	if err != nil {
		return err
	}
	names := make([]string, 0, len(entries))
	for _, entry := range entries {
		if !entry.IsDir() {
			names = append(names, entry.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		var applied bool
		if err := db.QueryRow(`SELECT EXISTS(SELECT 1 FROM lab_schema_migrations WHERE version=$1)`, name).Scan(&applied); err != nil {
			return err
		}
		if applied {
			continue
		}
		sqlText, err := files.ReadFile(name)
		if err != nil {
			return err
		}
		tx, err := db.Begin()
		if err != nil {
			return err
		}
		if _, err = tx.Exec(string(sqlText)); err != nil {
			tx.Rollback()
			return fmt.Errorf("apply %s: %w", name, err)
		}
		if _, err = tx.Exec(`INSERT INTO lab_schema_migrations(version) VALUES($1)`, name); err != nil {
			tx.Rollback()
			return err
		}
		if err = tx.Commit(); err != nil {
			return err
		}
	}
	return nil
}
