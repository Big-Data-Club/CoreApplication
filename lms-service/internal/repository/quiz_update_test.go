package repository

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"io"
	"strings"
	"testing"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/models"
)

// A recording SQL driver verifies transaction boundaries and scoped option
// writes without a shared database or production data.
type quizUpdateDriver struct{}
type quizUpdateConn struct {
	committed, rolledBack bool
	queries               []string
	args                  [][]driver.NamedValue
	rejectOption          bool
}
type quizUpdateTx struct{ conn *quizUpdateConn }
type quizUpdateRows struct{ done bool }

var _ driver.Conn = (*quizUpdateConn)(nil)

func (quizUpdateDriver) Open(string) (driver.Conn, error)     { return &quizUpdateConn{}, nil }
func (c *quizUpdateConn) Prepare(string) (driver.Stmt, error) { panic("unexpected Prepare") }
func (c *quizUpdateConn) Close() error                        { return nil }
func (c *quizUpdateConn) Begin() (driver.Tx, error)           { return &quizUpdateTx{c}, nil }
func (tx *quizUpdateTx) Commit() error                        { tx.conn.committed = true; return nil }
func (tx *quizUpdateTx) Rollback() error                      { tx.conn.rolledBack = true; return nil }
func (c *quizUpdateConn) QueryContext(_ context.Context, query string, args []driver.NamedValue) (driver.Rows, error) {
	c.queries = append(c.queries, query)
	c.args = append(c.args, args)
	return &quizUpdateRows{}, nil
}
func (c *quizUpdateConn) ExecContext(_ context.Context, query string, args []driver.NamedValue) (driver.Result, error) {
	c.queries = append(c.queries, query)
	c.args = append(c.args, args)
	if c.rejectOption && strings.Contains(query, "UPDATE quiz_answer_options") {
		return driver.RowsAffected(0), nil
	}
	return driver.RowsAffected(1), nil
}
func (r *quizUpdateRows) Columns() []string { return []string{"updated_at"} }
func (r *quizUpdateRows) Close() error      { return nil }
func (r *quizUpdateRows) Next(values []driver.Value) error {
	if r.done {
		return io.EOF
	}
	r.done = true
	values[0] = time.Now()
	return nil
}
func init() { sql.Register("quiz-update-test", quizUpdateDriver{}) }

func TestQuestionUpdateTransaction(t *testing.T) {
	for _, tc := range []struct {
		name    string
		options bool
		reject  bool
	}{
		{"omitted answers are preserved", false, false},
		{"existing option ID is updated in place", true, false},
		{"foreign option rolls back the question too", true, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			db, err := sql.Open("quiz-update-test", "")
			if err != nil {
				t.Fatal(err)
			}
			defer db.Close()
			db.SetMaxOpenConns(1)
			var conn *quizUpdateConn
			raw, err := db.Conn(context.Background())
			if err != nil {
				t.Fatal(err)
			}
			if err = raw.Raw(func(c interface{}) error { conn = c.(*quizUpdateConn); conn.rejectOption = tc.reject; return nil }); err != nil {
				t.Fatal(err)
			}
			raw.Close()
			question := &models.QuizQuestion{ID: 2, QuizID: 86, QuestionText: "Edited", OrderIndex: 2, IsRequired: true}
			var options *[]dto.UpdateAnswerOptionRequest
			if tc.options {
				list := []dto.UpdateAnswerOptionRequest{{ID: 20, OptionText: "Edited answer", IsCorrect: true, OrderIndex: 1}}
				options = &list
			}
			err = NewQuizRepository(db).UpdateQuestionWithAnswers(context.Background(), question, options, nil)
			if (err != nil) != tc.reject {
				t.Fatalf("unexpected error: %v", err)
			}
			if conn.committed == tc.reject || conn.rolledBack != tc.reject {
				t.Fatalf("commit=%v rollback=%v", conn.committed, conn.rolledBack)
			}
			if len(conn.args[0]) != 11 || conn.args[0][4].Value != int64(2) || conn.args[0][6].Value != true {
				t.Fatal("order or required flag changed")
			}
			if !tc.options && len(conn.queries) != 1 {
				t.Fatal("omitted answer lists were modified")
			}
			if tc.options {
				if !strings.Contains(conn.queries[1], "WHERE id=$6 AND question_id=$7") {
					t.Fatal("option update is not scoped to its question")
				}
				if conn.args[1][5].Value != int64(20) || conn.args[1][6].Value != int64(2) {
					t.Fatal("existing option identity changed")
				}
			}
		})
	}
}
