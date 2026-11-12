package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"example/hello/internal/dto"
	"fmt"
	_ "github.com/jackc/pgx/v5/stdlib"
	"os"
	"testing"
	"time"
)

// Set QUIZ_RESULTS_TEST_DSN to an isolated PostgreSQL database with CREATE SCHEMA.
// The fixture never accesses the application's public schema or real learners.
func TestQuizResultsIntegration(t *testing.T) {
	dsn := os.Getenv("QUIZ_RESULTS_TEST_DSN")
	if dsn == "" {
		t.Skip("QUIZ_RESULTS_TEST_DSN not configured")
	}
	db, err := sql.Open("pgx", dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	db.SetMaxOpenConns(1)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	schema := fmt.Sprintf("quiz_results_test_%d", time.Now().UnixNano())
	if _, err = db.ExecContext(ctx, "CREATE SCHEMA "+schema); err != nil {
		t.Fatal(err)
	}
	defer db.ExecContext(context.Background(), "DROP SCHEMA "+schema+" CASCADE")
	if _, err = db.ExecContext(ctx, "SET search_path TO "+schema); err != nil {
		t.Fatal(err)
	}
	fixture, err := os.ReadFile("testdata/quiz_results_fixture.sql")
	if err != nil {
		t.Fatal(err)
	}
	if _, err = db.ExecContext(ctx, string(fixture)); err != nil {
		t.Fatal(err)
	}
	report, err := NewQuizRepository(db).GetQuizResults(ctx, 42)
	if err != nil {
		t.Fatal(err)
	}
	var actual struct {
		Attempts []struct {
			ID    int64
			Focus json.RawMessage `json:"focus_summary"`
		}
		Questions []struct {
			ID                         int64
			Answered, Correct, Pending int
			Options                    []struct {
				Selected int `json:"selected_count"`
			} `json:"answer_options"`
		}
	}
	if err = json.Unmarshal(report, &actual); err != nil {
		t.Fatal(err)
	}
	if len(actual.Attempts) != 3 || len(actual.Questions) != 3 {
		t.Fatalf("lost records: %s", report)
	}
	q := actual.Questions[0]
	if q.Answered != 2 || q.Correct != 1 {
		t.Fatalf("in-progress attempts affected stats: %s", report)
	}
	if len(q.Options) != 2 || q.Options[0].Selected != 1 || q.Options[1].Selected != 1 {
		t.Fatalf("option distribution incorrect: %s", report)
	}
	if actual.Questions[1].Pending != 1 || actual.Questions[2].Pending != 0 {
		t.Fatalf("pending and skipped conflated: %s", report)
	}
	if string(actual.Attempts[1].Focus) != "null" {
		t.Fatalf("missing browser data fabricated: %s", report)
	}
	if _, err = db.ExecContext(ctx, `INSERT INTO quiz_attempts SELECT 1000+g,42,100+g,1,now(),now(),'GRADED',g%101,30,15,true,30,NULL FROM generate_series(1,1000) g`); err != nil {
		t.Fatal(err)
	}
	report, err = NewQuizRepository(db).GetQuizResults(ctx, 42)
	if err != nil {
		t.Fatal(err)
	}
	var page struct {
		Attempts []struct{ ID int64 }
		Students []struct {
			ID int64 `json:"student_id"`
		}
		Summary struct {
			Total int `json:"total_attempts"`
		}
		Total int `json:"attempts_total"`
	}
	if err = json.Unmarshal(report, &page); err != nil {
		t.Fatal(err)
	}
	if len(page.Attempts) != 50 || len(page.Students) != 50 || page.Summary.Total != 1003 || page.Total != 1003 {
		t.Fatalf("pagination lost whole-quiz metrics: %s", report)
	}
	filtered, err := NewQuizRepository(db).GetQuizResults(ctx, 42, dto.QuizResultsQuery{AttemptPage: 1, StudentPage: 1, Search: "Test learner"})
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(filtered, &page); err != nil {
		t.Fatal(err)
	}
	if len(page.Attempts) != 3 || len(page.Students) != 1 || page.Summary.Total != 1003 {
		t.Fatalf("search changed global metrics: %s", filtered)
	}

	narrow, err := NewQuizRepository(db).GetQuizResultRows(ctx, 42, dto.QuizResultsQuery{AttemptPage: 2, StudentPage: 2})
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(narrow, &page); err != nil {
		t.Fatal(err)
	}
	if len(page.Attempts) != 50 || len(page.Students) != 50 || page.Total != 1003 {
		t.Fatalf("narrow query page incorrect: %s", narrow)
	}
	narrow, err = NewQuizRepository(db).GetQuizResultRows(ctx, 42, dto.QuizResultsQuery{AttemptPage: 1, StudentPage: 1, Search: "Test learner"})
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(narrow, &page); err != nil {
		t.Fatal(err)
	}
	if len(page.Attempts) != 3 || len(page.Students) != 1 {
		t.Fatalf("narrow query search incorrect: %s", narrow)
	}

}
