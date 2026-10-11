package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/lib/pq"
	"lab-service/internal/runtime"
)

func TestCompleteGradingAtomicAndIdempotent(t *testing.T) {
	endpoint := os.Getenv("BDC_LAB_SQL_TEST_URL")
	if endpoint == "" {
		t.Skip("set BDC_LAB_SQL_TEST_URL to a disposable PostgreSQL instance")
	}
	db, err := sql.Open("postgres", endpoint)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	db.SetMaxOpenConns(1)
	ctx := context.Background()
	schema := fmt.Sprintf("grading_test_%d", time.Now().UnixNano())
	if _, err := db.ExecContext(ctx, "CREATE SCHEMA "+pq.QuoteIdentifier(schema)+"; SET search_path TO "+pq.QuoteIdentifier(schema)); err != nil {
		t.Fatal(err)
	}
	defer db.ExecContext(ctx, "DROP SCHEMA "+pq.QuoteIdentifier(schema)+" CASCADE")
	_, err = db.ExecContext(ctx, `CREATE TABLE lab_submissions(id bigserial PRIMARY KEY, lab_id bigint, user_id bigint, language text, code text, query text, script_content text, status text NOT NULL, score numeric, passed_tests integer, total_tests integer, runtime_ms integer, memory_kb integer, compiler_output text, graded_at timestamptz);
 CREATE TABLE submission_test_results(submission_id bigint, test_case_id bigint, status text CONSTRAINT submission_test_results_status_check CHECK(status IN ('PASSED','RUNTIME_ERROR')), actual_output text, runtime_ms integer, memory_kb integer, UNIQUE(submission_id,test_case_id));
 INSERT INTO lab_submissions(status) VALUES('PENDING');`)
	if err != nil {
		t.Fatal(err)
	}
	migration, err := os.ReadFile("../../migrations/V006__grading_compile_status.sql")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.ExecContext(ctx, string(migration)); err != nil {
		t.Fatal(err)
	}
	repo := NewSubmissionRepository(db)
	result := &runtime.ExecutionResult{Status: "COMPILE_ERROR", TotalTests: 2, TestResults: []runtime.TestResult{{TestCaseID: 1, Status: "PASSED"}, {TestCaseID: 2, Status: "INVALID"}}}
	if err := repo.CompleteGrading(ctx, 1, result); err == nil {
		t.Fatal("invalid second result did not fail")
	}
	var count int
	var status string
	if err := db.QueryRowContext(ctx, "SELECT count(*) FROM submission_test_results").Scan(&count); err != nil || count != 0 {
		t.Fatalf("partial results persisted: %d %v", count, err)
	}
	if err := db.QueryRowContext(ctx, "SELECT status FROM lab_submissions WHERE id=1").Scan(&status); err != nil || status != "PENDING" {
		t.Fatalf("partial verdict persisted: %s %v", status, err)
	}
	result.TestResults[1].Status = "COMPILE_ERROR"
	if err := repo.CompleteGrading(ctx, 1, result); err != nil {
		t.Fatal(err)
	}
	result.Status = "ACCEPTED"
	if err := repo.CompleteGrading(ctx, 1, result); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRowContext(ctx, "SELECT status FROM lab_submissions WHERE id=1").Scan(&status); err != nil || status != "COMPILE_ERROR" {
		t.Fatalf("duplicate replaced verdict: %s %v", status, err)
	}
	if err := db.QueryRowContext(ctx, "SELECT count(*) FROM submission_test_results").Scan(&count); err != nil || count != 2 {
		t.Fatalf("duplicate appended results: %d %v", count, err)
	}
	first, err := repo.CreatePracticeSubmission(ctx, 2, 3, "python", "print(1)", "", 1)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := repo.CreatePracticeSubmission(ctx, 2, 3, "python", "print(1)", "", 1); !errors.Is(err, ErrSubmissionLimit) {
		t.Fatalf("parallel/pending attempt bypassed limit: %v", err)
	}
	if _, err := db.ExecContext(ctx, "UPDATE lab_submissions SET status='FAILED' WHERE id=$1", first); err != nil {
		t.Fatal(err)
	}
	if _, err := repo.CreatePracticeSubmission(ctx, 2, 3, "python", "print(1)", "", 1); err != nil {
		t.Fatalf("infrastructure failure consumed attempt: %v", err)
	}

}
