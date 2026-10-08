package handler

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"example/hello/pkg/ai"
	"github.com/gin-gonic/gin"
)

func TestPersonalFlashcardHandlerInjectsOwner(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-AI-Secret") != "test-secret" {
			t.Error("missing internal auth")
		}
		body, _ := io.ReadAll(r.Body)
		if strings.Contains(string(body), `"student_id":999`) || !strings.Contains(string(body), `"student_id":42`) {
			t.Errorf("owner not injected: %s", body)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"decks":[],"cards":[]}`))
	}))
	defer upstream.Close()
	t.Setenv("AI_SERVICE_URL", upstream.URL)
	t.Setenv("AI_SERVICE_SECRET", "test-secret")
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(func(c *gin.Context) { c.Set("user_id", int64(42)); c.Next() })
	router.POST("/courses/:courseId/library", NewPersonalFlashcardHandler(ai.NewClient(), allowFlashcardCourse{}).Action)
	recorder := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/courses/7/library", strings.NewReader(`{"action":"list","student_id":999}`))
	req.Header.Set("Content-Type", "application/json")
	router.ServeHTTP(recorder, req)
	if recorder.Code != http.StatusOK {
		t.Fatalf("got %d: %s", recorder.Code, recorder.Body.String())
	}
}

func TestPersonalFlashcardHandlerRejectsMissingIdentityAndInternalActions(t *testing.T) {
	gin.SetMode(gin.TestMode)
	for _, tc := range []struct {
		identity bool
		action   string
		want     int
	}{
		{false, "list", http.StatusUnauthorized},
		{true, "queue_failed", http.StatusBadRequest},
		{true, "unknown", http.StatusBadRequest},
	} {
		router := gin.New()
		if tc.identity {
			router.Use(func(c *gin.Context) { c.Set("user_id", int64(42)); c.Next() })
		}
		router.POST("/courses/:courseId/library", NewPersonalFlashcardHandler(nil, allowFlashcardCourse{}).Action)
		recorder := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodPost, "/courses/7/library", strings.NewReader(`{"action":"`+tc.action+`"}`))
		req.Header.Set("Content-Type", "application/json")
		router.ServeHTTP(recorder, req)
		if recorder.Code != tc.want {
			t.Errorf("action %s: got %d want %d", tc.action, recorder.Code, tc.want)
		}
	}
}

type allowFlashcardCourse struct{}

func (allowFlashcardCourse) VerifyAccess(context.Context, int64, int64, string) error { return nil }

type denyFlashcardCourse struct{}

func (denyFlashcardCourse) VerifyAccess(context.Context, int64, int64, string) error {
	return fmt.Errorf("not enrolled")
}
func TestPersonalFlashcardsDenyUnenrolledCourse(t *testing.T) {
	r := gin.New()
	r.Use(func(c *gin.Context) { c.Set("user_id", int64(42)); c.Next() })
	r.POST("/courses/:courseId/library", NewPersonalFlashcardHandler(nil, denyFlashcardCourse{}).Action)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, httptest.NewRequest(http.MethodPost, "/courses/7/library", strings.NewReader(`{"action":"list"}`)))
	if w.Code != http.StatusForbidden {
		t.Fatalf("got %d", w.Code)
	}
}
