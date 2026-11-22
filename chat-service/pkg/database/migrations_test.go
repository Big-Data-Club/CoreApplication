package database

import (
	"os"
	"path/filepath"
	"testing"
)

func TestReleasePathsPreserveLedgerNamesAndOrder(t *testing.T) {
	dir := t.TempDir()
	for path, sql := range map[string]string{
		"releases/2026-11/V002.sql":      "SELECT 2;",
		"releases/2026-12/V001.sql":      "SELECT 1;",
		"releases/2026-11/manifest.json": "{}",
	} {
		full := filepath.Join(dir, path)
		if err := os.MkdirAll(filepath.Dir(full), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(full, []byte(sql), 0600); err != nil {
			t.Fatal(err)
		}
	}
	entries, err := readMigrationFiles(dir)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 2 || entries[0].Version != "V001.sql" || entries[0].SQL != "SELECT 1;" || entries[1].Version != "V002.sql" {
		t.Fatalf("release folders changed migration identities/order: %#v", entries)
	}
	if err := os.WriteFile(filepath.Join(dir, "V001.sql"), []byte("SELECT 3;"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := readMigrationFiles(dir); err == nil {
		t.Fatal("duplicate ledger identity accepted")
	}
}
