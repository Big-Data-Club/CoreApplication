package handler

import (
	"context"
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"

	"example/hello/internal/middleware"
	"example/hello/internal/service"
	"github.com/gin-gonic/gin"
)

type quizIndexStub struct {
	calls   int
	user    int64
	request service.QuizIndexRequest
	denied  bool
}

func (s *quizIndexStub) QuizIndexAction(_ context.Context, _ int64, user int64, _ string, _ string, request service.QuizIndexRequest) (json.RawMessage, error) {
	s.calls++
	s.user = user
	s.request = request
	if s.denied {
		return nil, service.ErrQuizAccess
	}
	return json.RawMessage(`{"status":"pending"}`), nil
}
func (s *quizIndexStub) QuizIndexSource(context.Context, int64, int64, int64, bool) (interface{}, error) {
	s.calls++
	return map[string]string{"data": "private"}, nil
}

func TestQuizIndexBoundary(t *testing.T) {
	gin.SetMode(gin.TestMode)
	stub := &quizIndexStub{}
	h := NewQuizIndexHandler(stub)
	engine := gin.New()
	engine.POST("/quizzes/:quizId/index", func(c *gin.Context) { c.Set("user_id", int64(7)); c.Set("user_role", "TEACHER") }, h.Action("queue"))
	internal := engine.Group("/internal")
	internal.Use(middleware.ServiceOnlyMiddleware("test-service-secret"))
	internal.GET("/quizzes/:quizId/index-source", h.Source)
	request := httptest.NewRequest("POST", "/quizzes/42/index", strings.NewReader(`{"course_id":999,"requester_id":123}`))
	request.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	engine.ServeHTTP(w, request)
	if w.Code != 200 || stub.user != 7 {
		t.Fatalf("client replaced authenticated subject: %d %+v", w.Code, stub)
	}
	stub.denied = true
	request = httptest.NewRequest("POST", "/quizzes/42/index", strings.NewReader(`{}`))
	request.Header.Set("Content-Type", "application/json")
	w = httptest.NewRecorder()
	engine.ServeHTTP(w, request)
	if w.Code != 403 {
		t.Fatalf("foreign manager access: %d", w.Code)
	}
	calls := stub.calls
	request = httptest.NewRequest("GET", "/internal/quizzes/42/index-source?user_id=7", nil)
	request.Header.Set("Authorization", "Bearer fake-user-token")
	w = httptest.NewRecorder()
	engine.ServeHTTP(w, request)
	if w.Code != 401 || stub.calls != calls {
		t.Fatal("user JWT reached service-only source")
	}
	request = httptest.NewRequest("POST", "/quizzes/42/index", strings.NewReader(`{"query":"`+strings.Repeat("a", 20000)+`"}`))
	request.Header.Set("Content-Type", "application/json")
	w = httptest.NewRecorder()
	engine.ServeHTTP(w, request)
	if w.Code != 400 || stub.calls != calls {
		t.Fatal("oversized payload reached service")
	}
}
