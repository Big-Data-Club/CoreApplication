package middleware

import (
	"context"
	"database/sql"
	"fmt"
	"github.com/gin-gonic/gin"
	"github.com/lib/pq"
	"net/http/httptest"
	"os"
	"testing"
	"time"
)

func TestLabAuthorOwnResourceOnly(t *testing.T) {
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
	schema := fmt.Sprintf("author_test_%d", time.Now().UnixNano())
	ctx := context.Background()
	if _, err = db.ExecContext(ctx, "CREATE SCHEMA "+pq.QuoteIdentifier(schema)+"; SET search_path TO "+pq.QuoteIdentifier(schema)); err != nil {
		t.Fatal(err)
	}
	defer db.ExecContext(ctx, "DROP SCHEMA "+pq.QuoteIdentifier(schema)+" CASCADE")
	_, err = db.ExecContext(ctx, `CREATE TABLE labs(id bigint,created_by bigint); INSERT INTO labs VALUES(1,7),(2,8);
 CREATE TABLE lab_test_cases(id bigint,lab_id bigint);INSERT INTO lab_test_cases VALUES(3,1),(4,2);`)
	if err != nil {
		t.Fatal(err)
	}
	gin.SetMode(gin.TestMode)
	for _, test := range []struct {
		path   string
		userID int64
		role   string
		want   int
	}{{"/labs/1", 7, "TEACHER", 200}, {"/labs/2", 7, "TEACHER", 403}, {"/labs/999", 7, "TEACHER", 404}, {"/cases/3", 7, "TEACHER", 200}, {"/cases/4", 7, "TEACHER", 403}, {"/cases/4", 7, "ADMIN", 200}} {
		router := gin.New()
		router.Use(func(c *gin.Context) { c.Set("user_id", test.userID); c.Set("user_role", test.role) })
		done := func(c *gin.Context) { c.Status(200) }
		router.GET("/labs/:labId", LabAuthor(db, "lab"), done)
		router.GET("/cases/:id", LabAuthor(db, "case"), done)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, httptest.NewRequest("GET", test.path, nil))
		if w.Code != test.want {
			t.Errorf("%s got %d want %d", test.path, w.Code, test.want)
		}
	}
}
