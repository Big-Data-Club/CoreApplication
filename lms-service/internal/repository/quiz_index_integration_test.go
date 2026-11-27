package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	"example/hello/migrations"
)

func TestQuizIndexSourceAndAssessmentSnapshot(t *testing.T) {
	dsn := os.Getenv("QUIZ_RESULTS_TEST_DSN")
	if dsn == "" {
		t.Skip("isolated PostgreSQL not configured")
	}
	db, err := sql.Open("pgx", dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	db.SetMaxOpenConns(1)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	schema := fmt.Sprintf("quiz_index_test_%d", time.Now().UnixNano())
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
	if _, err = db.ExecContext(ctx, `ALTER TABLE quiz_questions ADD COLUMN updated_at timestamp DEFAULT now()`); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 2; i++ {
		if _, err = db.ExecContext(ctx, migrations.QuizAssessmentSnapshot); err != nil {
			t.Fatal(err)
		}
	}
	repo := NewQuizRepository(db)
	head, err := repo.QuizIndexSource(ctx, 42, 0, true)
	if err != nil {
		t.Fatal(err)
	}
	var first struct {
		Revision string
		Total    int
	}
	if err = json.Unmarshal(head, &first); err != nil {
		t.Fatal(err)
	}
	page, err := repo.QuizIndexSource(ctx, 42, 0, false)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(page), "is_correct") || strings.Contains(string(page), "correct_answers") {
		t.Fatalf("answer key escaped: %s", page)
	}
	var questions []struct {
		ID   int64
		Hash string `json:"source_hash"`
	}
	if err = json.Unmarshal(page, &questions); err != nil {
		t.Fatal(err)
	}
	if err = repo.SetQuizQuestionNode(ctx, 42, 1, 202, questions[0].Hash); err != nil {
		t.Fatal(err)
	}
	if err = repo.SetQuizQuestionNode(ctx, 42, 1, 303, questions[0].Hash); err == nil {
		t.Fatal("stale proposal overwrote question")
	}
	head, err = repo.QuizIndexSource(ctx, 42, 0, true)
	if err != nil {
		t.Fatal(err)
	}
	var next struct{ Revision string }
	json.Unmarshal(head, &next)
	if next.Revision == first.Revision {
		t.Fatal("node edit did not invalidate index")
	}
	if _, err = db.ExecContext(ctx, `INSERT INTO quiz_student_answers(id,attempt_id,question_id,answer_data) VALUES(100,1,1,'{}')`); err != nil {
		t.Fatal(err)
	}
	if _, err = db.ExecContext(ctx, `UPDATE quiz_questions SET node_id=303,points=20 WHERE id=1`); err != nil {
		t.Fatal(err)
	}
	var node int64
	var maximum float64
	if err = db.QueryRowContext(ctx, `SELECT assessed_node_id,assessed_max_points FROM quiz_student_answers WHERE id=100`).Scan(&node, &maximum); err != nil {
		t.Fatal(err)
	}
	if node != 202 || maximum != 10 {
		t.Fatalf("assessment changed retrospectively: node=%d max=%f", node, maximum)
	}
	if _, err = db.ExecContext(ctx, `INSERT INTO quiz_questions(id,quiz_id,question_text,points) SELECT 100+g,42,'Synthetic',1 FROM generate_series(1,205) g`); err != nil {
		t.Fatal(err)
	}
	seen := map[int64]bool{}
	var after int64
	for {
		page, err = repo.QuizIndexSource(ctx, 42, after, false)
		if err != nil {
			t.Fatal(err)
		}
		if err = json.Unmarshal(page, &questions); err != nil {
			t.Fatal(err)
		}
		if len(questions) == 0 {
			break
		}
		if len(questions) > 100 {
			t.Fatal("unbounded page")
		}
		for _, q := range questions {
			if seen[q.ID] || q.ID <= after {
				t.Fatal("duplicate/out-of-order page")
			}
			seen[q.ID] = true
		}
		after = questions[len(questions)-1].ID
	}
	if len(seen) != 208 {
		t.Fatalf("pagination lost questions: %d", len(seen))
	}
}
