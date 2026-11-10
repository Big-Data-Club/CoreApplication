package handler

import (
	"database/sql"
	"strings"

	"example/hello/internal/service"
	_ "github.com/jackc/pgx/v5/stdlib"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestFarmLearningRejectsBrowserWithoutInternalSecret(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := NewFarmLearningHandler(nil, "private-service-secret")
	r := gin.New()
	g := r.Group("/internal/farm", h.Authenticate)
	g.GET("/question", h.Question)
	for _, supplied := range []string{"", "wrong"} {
		req := httptest.NewRequest(http.MethodGet, "/internal/farm/question?user_id=41&kind=quiz", nil)
		if supplied != "" {
			req.Header.Set("X-API-Secret", supplied)
		}
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)
		if w.Code != http.StatusUnauthorized {
			t.Fatalf("secret %q: status %d", supplied, w.Code)
		}
	}
}

func TestFarmAttemptFailureIsLoggedPrivately(t *testing.T) {
	gin.SetMode(gin.TestMode)
	db, err := sql.Open("pgx", "postgres://unused/unused")
	if err != nil {
		t.Fatal(err)
	}
	// A closed database deterministically fails without any network access.
	db.Close()
	h := NewFarmLearningHandler(service.NewFarmLearningService(db, nil, nil), "secret")
	r := gin.New()
	var privateError string
	r.Use(func(c *gin.Context) {
		c.Next()
		privateError = c.Errors.ByType(gin.ErrorTypePrivate).String()
	})
	r.POST("/attempt", h.Attempt)
	payload := `{"challenge_id":"123e4567-e89b-12d3-a456-426614174000","user_id":41,"course_id":9,"source_id":"lms:quiz:7","kind":"quiz"}`
	req := httptest.NewRequest(http.MethodPost, "/attempt", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	if w.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d", w.Code)
	}
	if !strings.Contains(privateError, "database is closed") || !strings.Contains(privateError, "123e4567-e89b-12d3-a456-426614174000") {
		t.Fatalf("missing diagnostic context: %s", privateError)
	}
	if strings.Contains(w.Body.String(), "database") {
		t.Fatalf("private error leaked: %s", w.Body.String())
	}
}
