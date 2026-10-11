package repository

import (
	"context"
	"database/sql"
	"fmt"
	"github.com/lib/pq"
	"lab-service/internal/dto"
	"os"
	"testing"
	"time"
)

func TestTestSuiteAtomicReplacementAndStaleDraft(t *testing.T) {
	endpoint := os.Getenv("BDC_LAB_SQL_TEST_URL")
	if endpoint == "" {
		t.Skip("requires disposable PostgreSQL")
	}
	db, err := sql.Open("postgres", endpoint)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	db.SetMaxOpenConns(1)
	ctx := context.Background()
	schema := fmt.Sprintf("suite_test_%d", time.Now().UnixNano())
	if _, err = db.ExecContext(ctx, "CREATE SCHEMA "+pq.QuoteIdentifier(schema)+"; SET search_path TO "+pq.QuoteIdentifier(schema)); err != nil {
		t.Fatal(err)
	}
	defer db.ExecContext(ctx, "DROP SCHEMA "+pq.QuoteIdentifier(schema)+" CASCADE")
	_, err = db.ExecContext(ctx, `CREATE TABLE labs(id bigint PRIMARY KEY); INSERT INTO labs VALUES(1);
 CREATE TABLE lab_test_cases(id bigserial PRIMARY KEY,lab_id bigint REFERENCES labs(id),name varchar(255),order_index integer,is_sample boolean,is_hidden boolean,weight integer,input text,expected text CHECK(expected!='FAIL_DATABASE'),time_limit_ms integer,memory_limit_mb integer,explanation text,created_at timestamptz DEFAULT now());`)
	if err != nil {
		t.Fatal(err)
	}
	repo := NewTestCaseRepository(db)
	cases := []dto.CreateTestCaseRequest{{Name: "First", Input: "[1]", Expected: "1"}, {Name: "Second", Expected: "FAIL_DATABASE"}}
	if _, err = repo.BulkCreate(ctx, 1, cases); err == nil {
		t.Fatal("invalid second insert accepted")
	}
	saved, _ := repo.ListByLab(ctx, 1, false)
	if len(saved) != 0 {
		t.Fatal("partial import persisted")
	}
	cases[1].Expected = "4"
	saved, err = repo.BulkCreate(ctx, 1, cases)
	if err != nil {
		t.Fatal(err)
	}
	ids := []int64{saved[0].ID, saved[1].ID}
	if _, err = db.ExecContext(ctx, "CREATE TABLE submission_test_results(test_case_id bigint REFERENCES lab_test_cases(id))"); err != nil {
		t.Fatal(err)
	}
	if _, err = db.ExecContext(ctx, "INSERT INTO submission_test_results VALUES($1)", saved[0].ID); err != nil {
		t.Fatal(err)
	}

	revision := SuiteRevision(saved)
	if _, err = db.ExecContext(ctx, "UPDATE lab_test_cases SET expected='2' WHERE id=$1", saved[0].ID); err != nil {
		t.Fatal(err)
	}
	if _, err = repo.Replace(ctx, 1, dto.ReplaceTestCasesRequest{ExpectedIDs: ids, ExpectedRevision: revision, TestCases: cases}); err == nil {
		t.Fatal("content changed with same IDs but stale draft overwrote it")
	}

	if _, err = repo.Replace(ctx, 1, dto.ReplaceTestCasesRequest{ExpectedIDs: ids[:1], TestCases: cases}); err == nil {
		t.Fatal("stale snapshot replaced suite")
	}
	cases[1].Expected = "FAIL_DATABASE"
	if _, err = repo.Replace(ctx, 1, dto.ReplaceTestCasesRequest{ExpectedIDs: ids, TestCases: cases}); err == nil {
		t.Fatal("invalid replacement accepted")
	}
	saved, _ = repo.ListByLab(ctx, 1, false)
	if len(saved) != 2 || saved[0].ID != ids[0] || saved[0].Expected != "2" {
		t.Fatal("failed replacement deleted existing cases")
	}
	cases = cases[:1]
	saved, err = repo.Replace(ctx, 1, dto.ReplaceTestCasesRequest{ExpectedIDs: ids, TestCases: cases})
	if err != nil || len(saved) != 1 || saved[0].ID != ids[0] {
		t.Fatalf("valid replacement failed: %v", err)
	}
}
