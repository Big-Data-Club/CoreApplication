package database

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type migrationEntry struct {
	Version string
	SQL     string
}

// readMigrationFiles reads all .sql files from dir, sorts them lexicographically,
// and returns them as migrationEntry slices.
func readMigrationFiles(dir string) ([]migrationEntry, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("migrations: read dir %q: %w", dir, err)
	}

	var files []string
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".sql") {
			files = append(files, e.Name())
		}
	}
	sort.Strings(files)

	var migrations []migrationEntry
	for _, name := range files {
		path := filepath.Join(dir, name)
		data, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("migrations: read %s: %w", name, err)
		}
		migrations = append(migrations, migrationEntry{
			Version: name,
			SQL:     string(data),
		})
	}
	return migrations, nil
}
