package repository

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"encoding/json"
	"io"
	"testing"
	"time"

	"example/hello/internal/models"
)

type quizFocusDriver struct{}
type quizFocusConn struct{ focus driver.Value }
type quizFocusRows struct {
	focus driver.Value
	done  bool
}

func (quizFocusDriver) Open(name string) (driver.Conn, error) {
	var focus driver.Value
	if name == "json" {
		focus = []byte(`{"departures":2,"away_seconds":5}`)
	}
	return &quizFocusConn{focus: focus}, nil
}
func (*quizFocusConn) Prepare(string) (driver.Stmt, error) { panic("unexpected prepare") }
func (*quizFocusConn) Close() error                        { return nil }
func (*quizFocusConn) Begin() (driver.Tx, error)           { panic("unexpected transaction") }
func (c *quizFocusConn) QueryContext(context.Context, string, []driver.NamedValue) (driver.Rows, error) {
	return &quizFocusRows{focus: c.focus}, nil
}
func (*quizFocusRows) Columns() []string {
	return []string{"id", "quiz_id", "student_id", "attempt_number", "started_at", "submitted_at", "time_spent_seconds", "total_points", "earned_points", "percentage", "is_passed", "status", "auto_graded_at", "manually_graded_at", "graded_by", "ip_address", "user_agent", "created_at", "updated_at", "focus_summary"}
}
func (*quizFocusRows) Close() error { return nil }
func (r *quizFocusRows) Next(values []driver.Value) error {
	if r.done {
		return io.EOF
	}
	r.done = true
	values[0], values[1], values[2], values[3] = int64(404), int64(86), int64(2), int64(1)
	values[4], values[11], values[17], values[18], values[19] = time.Now(), "IN_PROGRESS", time.Now(), time.Now(), r.focus
	return nil
}
func init() { sql.Register("quiz-focus-scan-test", quizFocusDriver{}) }

// Use database/sql's real Scan conversion, including PostgreSQL's nil for SQL NULL.
func TestQuizAttemptReadsNullableFocusSummary(t *testing.T) {
	for _, stored := range []string{"null", "json"} {
		t.Run(stored, func(t *testing.T) {
			db, err := sql.Open("quiz-focus-scan-test", stored)
			if err != nil {
				t.Fatal(err)
			}
			defer db.Close()
			repo := NewQuizRepository(db)
			check := func(attempt *models.QuizAttempt, err error) {
				t.Helper()
				if err != nil {
					t.Fatal(err)
				}
				if attempt == nil || attempt.ID != 404 {
					t.Fatalf("unexpected attempt: %+v", attempt)
				}
				if stored == "null" {
					if len(attempt.FocusSummary) != 0 {
						t.Fatalf("SQL NULL must stay empty: %s", attempt.FocusSummary)
					}
				} else {
					var summary struct {
						Departures int `json:"departures"`
					}
					if err := json.Unmarshal(attempt.FocusSummary, &summary); err != nil || summary.Departures != 2 {
						t.Fatalf("lost focus JSON: %s (%v)", attempt.FocusSummary, err)
					}
				}
			}
			check(repo.GetAttempt(context.Background(), 404))
			check(repo.GetStudentLatestAttempt(context.Background(), 86, 2))
			attempts, err := repo.ListStudentAttempts(context.Background(), 86, 2)
			if err != nil {
				t.Fatal(err)
			}
			if len(attempts) != 1 {
				t.Fatalf("got %d attempts", len(attempts))
			}
			check(&attempts[0], nil)
		})
	}
}
