package middleware

import (
	"context"
	"errors"
	"github.com/gin-gonic/gin"
	"net/http/httptest"
	"testing"
)

func TestChatRateLimitSeparatesReadsAndWrites(t *testing.T) {
	gin.SetMode(gin.TestMode)
	counts := map[string]int64{}
	router := gin.New()
	router.Use(func(c *gin.Context) { c.Set("user_id", int64(42)) }, chatRateLimit(func(ctx context.Context, key string) (int64, error) {
		if _, ok := ctx.Deadline(); !ok {
			t.Fatal("Redis call unbounded")
		}
		counts[key]++
		return counts[key], nil
	}, 2, 1))
	router.GET("/chat", func(c *gin.Context) { c.Status(204) })
	router.POST("/chat", func(c *gin.Context) { c.Status(204) })
	for _, step := range []struct {
		method string
		status int
	}{{"GET", 204}, {"GET", 204}, {"POST", 204}, {"GET", 429}, {"POST", 429}} {
		response := httptest.NewRecorder()
		router.ServeHTTP(response, httptest.NewRequest(step.method, "/chat", nil))
		if response.Code != step.status {
			t.Fatalf("%s got %d", step.method, response.Code)
		}
		if step.status == 429 && response.Header().Get("Retry-After") == "" {
			t.Fatal("missing retry hint")
		}
	}
	if counts["chat:rate:read:42"] != 3 || counts["chat:rate:write:42"] != 2 {
		t.Fatal("budgets mixed")
	}
}

func TestChatRateLimitDependencyFailure(t *testing.T) {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(chatRateLimit(func(context.Context, string) (int64, error) { return 0, errors.New("redis unavailable") }, 2, 1))
	router.POST("/chat", func(c *gin.Context) { t.Fatal("mutation reached handler without capacity check") })
	response := httptest.NewRecorder()
	router.ServeHTTP(response, httptest.NewRequest("POST", "/chat", nil))
	if response.Code != 503 {
		t.Fatalf("got %d", response.Code)
	}
}
