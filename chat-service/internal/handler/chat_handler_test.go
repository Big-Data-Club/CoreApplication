package handler

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"chat-service/internal/repository"
	"github.com/gin-gonic/gin"
)

// A scripted SQL boundary exercises real repositories without a running DB.
type queryResult struct {
	values []driver.Value
	err    error
}
type testConnection struct {
	results         []queryResult
	queries, writes int
}
type testConnector struct{ conn *testConnection }
type testDriver struct{}

func (testDriver) Open(string) (driver.Conn, error)                  { return nil, errors.New("use connector") }
func (c testConnector) Connect(context.Context) (driver.Conn, error) { return c.conn, nil }
func (testConnector) Driver() driver.Driver                          { return testDriver{} }
func (*testConnection) Prepare(string) (driver.Stmt, error) {
	return nil, errors.New("unexpected prepare")
}
func (*testConnection) Close() error              { return nil }
func (*testConnection) Begin() (driver.Tx, error) { return nil, errors.New("unexpected transaction") }
func (c *testConnection) ExecContext(context.Context, string, []driver.NamedValue) (driver.Result, error) {
	c.writes++
	return driver.RowsAffected(1), nil
}
func (c *testConnection) QueryContext(context.Context, string, []driver.NamedValue) (driver.Rows, error) {
	c.queries++
	if len(c.results) == 0 {
		return nil, errors.New("unexpected query")
	}
	result := c.results[0]
	c.results = c.results[1:]
	if result.err != nil {
		return nil, result.err
	}
	return &testRows{values: result.values}, nil
}

type testRows struct {
	values []driver.Value
	read   bool
}

func (r *testRows) Columns() []string {
	cols := make([]string, len(r.values))
	for i := range cols {
		cols[i] = "value"
	}
	return cols
}
func (*testRows) Close() error { return nil }
func (r *testRows) Next(dest []driver.Value) error {
	if r.read {
		return io.EOF
	}
	copy(dest, r.values)
	r.read = true
	return nil
}

func TestSendPermissionValidationAndPersistenceFailure(t *testing.T) {
	gin.SetMode(gin.TestMode)
	for _, step := range []struct {
		name, body              string
		results                 []queryResult
		status, queries, writes int
	}{
		{"write without read", `{"body":"hello"}`, []queryResult{{values: []driver.Value{false}}, {values: []driver.Value{false, true}}}, 403, 2, 0},
		{"malformed body", `{"body":42}`, []queryResult{{values: []driver.Value{true}}}, 400, 1, 0},
		{"oversized Unicode", `{"body":"` + strings.Repeat("ê", 4001) + `"}`, []queryResult{{values: []driver.Value{true}}}, 400, 1, 0},
		{"storage failure", `{"body":"hello"}`, []queryResult{{values: []driver.Value{true}}, {err: errors.New("database write unavailable")}}, 500, 2, 1},
	} {
		t.Run(step.name, func(t *testing.T) {
			conn := &testConnection{results: step.results}
			db := sql.OpenDB(testConnector{conn})
			defer db.Close()
			// A nil hub would panic if delivery ran before persistence succeeded.
			h := NewChatHandler(repository.NewChatRepository(db), repository.NewUserRepository(db), nil, nil, "")
			router := gin.New()
			router.Use(func(c *gin.Context) {
				c.Set("user_id", int64(7))
				c.Set("user_roles", []string{"STUDENT"})
				c.Set("user_email", "test@bdc.example")
			})
			router.POST("/channels/:id/messages", h.SendMessage)
			request := httptest.NewRequest("POST", "/channels/1/messages", strings.NewReader(step.body))
			request.Header.Set("Content-Type", "application/json")
			response := httptest.NewRecorder()
			router.ServeHTTP(response, request)
			if response.Code != step.status {
				t.Fatalf("got %d: %s", response.Code, response.Body.String())
			}
			if conn.queries != step.queries || conn.writes != step.writes {
				t.Fatalf("unexpected DB activity: queries=%d writes=%d", conn.queries, conn.writes)
			}
		})
	}
}

func TestWebSocketRejectsMissingIdentityBeforeDatabase(t *testing.T) {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	h := NewChatHandler(nil, nil, nil, nil, "test-secret")
	router.GET("/chat/ws", h.ServeWS)
	response := httptest.NewRecorder()
	router.ServeHTTP(response, httptest.NewRequest("GET", "/chat/ws", nil))
	if response.Code != 401 {
		t.Fatalf("got %d", response.Code)
	}
}
