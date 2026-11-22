package database

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type migrationEntry struct {
	Version string
	SQL     string
}

// Release directories are organizational; the ledger keeps the original basename
// and global lexicographic order, independent of the containing release folder.
func readMigrationFiles(dir string) ([]migrationEntry, error) {
	paths := make(map[string]string)
	err := filepath.WalkDir(dir, func(path string, entry fs.DirEntry, err error) error {
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
	if err != nil {
		return nil, fmt.Errorf("migrations: read dir %q: %w", dir, err)
	}
	names := make([]string, 0, len(paths))
	for name := range paths {
		names = append(names, name)
	}
	sort.Strings(names)
	var migrations []migrationEntry
	for _, name := range names {
		data, err := os.ReadFile(paths[name])
		if err != nil {
			return nil, fmt.Errorf("migrations: read %s: %w", name, err)
		}
		migrations = append(migrations, migrationEntry{Version: name, SQL: string(data)})
	}
	return migrations, nil
}
