package migrations

import (
	"database/sql"
	"embed"
	"fmt"
	"io/fs"
	"sort"
	"strings"
)

//go:embed releases
var files embed.FS

func Apply(db *sql.DB) error {
	if _, err := db.Exec(`CREATE TABLE IF NOT EXISTS lab_schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())`); err != nil {
		return err
	}
	paths, err := migrationPaths(files)
	if err != nil {
		return err
	}
	names := make([]string, 0, len(paths))
	for name := range paths {
		names = append(names, name)
	}
	sort.Strings(names)
	if err := baselineLegacySchema(db, names); err != nil {
		return err
	}
	for _, name := range names {
		var applied bool
		if err := db.QueryRow(`SELECT EXISTS(SELECT 1 FROM lab_schema_migrations WHERE version=$1)`, name).Scan(&applied); err != nil {
			return err
		}
		if applied {
			continue
		}
		sqlText, err := files.ReadFile(paths[name])
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

// Older production environments were initialized by PostgreSQL Docker scripts,
// before this service owned its migration history.  Their tables are real and
// must not be replayed merely because lab_schema_migrations is new.  Baseline
// only the known historical migrations, then let subsequent migrations (such
// as runtime tasks) run normally and transactionally.
func baselineLegacySchema(db *sql.DB, names []string) error {
	var historyCount int
	if err := db.QueryRow(`SELECT COUNT(*) FROM lab_schema_migrations`).Scan(&historyCount); err != nil {
		return err
	}
	if historyCount != 0 {
		return nil
	}
	var hasLabs bool
	if err := db.QueryRow(`SELECT to_regclass('public.labs') IS NOT NULL`).Scan(&hasLabs); err != nil {
		return err
	}
	if !hasLabs {
		return nil
	}
	tx, err := db.Begin()
	if err != nil {
		return err
	}
	for _, name := range names {
		if name >= "V005__runtime_tasks.sql" {
			break
		}
		if _, err := tx.Exec(`INSERT INTO lab_schema_migrations(version) VALUES($1) ON CONFLICT DO NOTHING`, name); err != nil {
			tx.Rollback()
			return fmt.Errorf("baseline %s: %w", name, err)
		}
	}
	return tx.Commit()
}

// Keep the historical basename in lab_schema_migrations, never the release path.
func migrationPaths(source fs.FS) (map[string]string, error) {
	paths := make(map[string]string)
	err := fs.WalkDir(source, ".", func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if !entry.IsDir() && strings.HasSuffix(entry.Name(), ".sql") {
			if _, exists := paths[entry.Name()]; exists {
				return fmt.Errorf("duplicate migration name: %s", entry.Name())
			}
			paths[entry.Name()] = path
		}
		return nil
	})
	return paths, err
}
