package runtime

import (
	"context"
	"database/sql"
	"os"
	"strings"
	"testing"

	"lab-service/internal/config"
)

func TestSQLComparisonPreservesValuesDuplicatesAndQuotedNewlines(t *testing.T) {
	for _, tc := range []struct {
		actual, expected string
		ordered, want    bool
	}{
		{"id\n2\n1\n", "id\n1\n2\n", false, true},
		{"id\n2\n1\n", "id\n1\n2\n", true, false},
		{"id\n1\n1\n", "id\n1\n2\n", false, false},
		{"name\n a \n", "name\na\n", false, false},
		{"name\na;b\n", "name\n\"a,b\"\n", false, false},
		{"name\n\"two\nlines\"\n", "name\n\"two\nlines\"\n", false, true},
	} {
		if got := compareSQLRows(tc.actual, tc.expected, tc.ordered); got != tc.want {
			t.Fatalf("actual=%q expected=%q got=%v", tc.actual, tc.expected, got)
		}
	}
}

// Use only a disposable local PostgreSQL instance. No application data is needed.
func TestPostgresPracticeIntegration(t *testing.T) {
	endpoint := os.Getenv("BDC_LAB_SQL_TEST_URL")
	if endpoint == "" {
		t.Skip("set BDC_LAB_SQL_TEST_URL to a disposable PostgreSQL instance")
	}
	r := NewDatabaseRunner(config.DatabaseLabConfig{PostgresURL: endpoint})
	admin, err := sql.Open("postgres", endpoint)
	if err != nil {
		t.Fatal(err)
	}
	defer admin.Close()
	ctx := context.Background()
	_, err = admin.ExecContext(ctx, "CREATE SCHEMA private_test; CREATE TABLE private_test.secret(value text); INSERT INTO private_test.secret VALUES ('private')")
	if err != nil {
		t.Fatal(err)
	}
	defer admin.ExecContext(ctx, "DROP SCHEMA private_test CASCADE")
	base := ExecutionRequest{Query: "SELECT id, name FROM people", SchemaSQL: "CREATE TABLE people(id integer, name text);", SeedSQL: "INSERT INTO people VALUES(2, 'b;two'),(1, 'a');", TestCases: []TestCase{{ID: 1, Expected: "id,name\n1,a\n2,b;two\n"}}}
	for _, tc := range []struct {
		name, query, want string
		ms                int
	}{
		{"accepted", base.Query, "ACCEPTED", 2000},
		{"wrong answer", "SELECT id, name FROM people WHERE id=1", "WRONG_ANSWER", 2000},
		{"syntax error", "SELEC id FROM people", "RUNTIME_ERROR", 2000},
		{"read-only", "DELETE FROM people RETURNING id", "RUNTIME_ERROR", 2000},
		{"other schema", "SELECT * FROM private_test.secret", "RUNTIME_ERROR", 2000},
		{"privilege escalation", "SET ROLE sql_practice_admin; SELECT * FROM private_test.secret", "RUNTIME_ERROR", 2000},
		{"timeout", "SELECT pg_sleep(1)", "TIME_LIMIT", 50},
		{"row cap", "SELECT generate_series(1,1001)", "RUNTIME_ERROR", 2000},
		{"large cell", "SELECT repeat('x', 100000)", "RUNTIME_ERROR", 2000},
	} {
		t.Run(tc.name, func(t *testing.T) {
			req := base
			req.Query = tc.query
			req.RuntimeConfig = map[string]interface{}{"time_limit_ms": tc.ms}
			result, err := r.Execute(ctx, req)
			if err != nil {
				t.Fatal(err)
			}
			if result.Status != tc.want {
				t.Fatalf("want %s got %+v", tc.want, result)
			}
		})
	}
	// Per-case input adds fixture rows and is reset before the next case.
	base.TestCases = []TestCase{{ID: 1, Input: "INSERT INTO people VALUES(3, 'c');", Expected: "id,name\n1,a\n2,b;two\n3,c\n"}, {ID: 2, Expected: "id,name\n1,a\n2,b;two\n"}}
	result, err := r.Execute(ctx, base)
	if err != nil || result.Status != "ACCEPTED" || result.PassedTests != 2 {
		t.Fatalf("fixture isolation result=%+v err=%v", result, err)
	}
	var leftovers int
	if err := admin.QueryRowContext(ctx, "SELECT count(*) FROM pg_roles WHERE rolname LIKE 'sql_learner_%'").Scan(&leftovers); err != nil || leftovers != 0 {
		t.Fatalf("learner roles leaked: %d %v", leftovers, err)
	}
	// Fixture errors are infrastructure/authoring errors, not student verdicts.
	base.SchemaSQL = "BROKEN SQL"
	_, err = r.Execute(ctx, base)
	if err == nil || !strings.Contains(err.Error(), "fixture") {
		t.Fatalf("bad fixture error=%v", err)
	}
}
