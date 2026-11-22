package migrations

import (
	"testing"
	"testing/fstest"
)

func TestReleasePathsKeepLegacyLedgerIdentities(t *testing.T) {
	paths, err := migrationPaths(files)
	if err != nil {
		t.Fatal(err)
	}
	if len(paths) != 6 || paths["V005__runtime_tasks.sql"] != "releases/2026-11/V005__runtime_tasks.sql" {
		t.Fatalf("embedded release lost legacy identities: %#v", paths)
	}
	_, err = migrationPaths(fstest.MapFS{
		"releases/one/V001.sql": &fstest.MapFile{Data: []byte("SELECT 1;")},
		"releases/two/V001.sql": &fstest.MapFile{Data: []byte("SELECT 2;")},
	})
	if err == nil {
		t.Fatal("duplicate ledger identity accepted")
	}
}
