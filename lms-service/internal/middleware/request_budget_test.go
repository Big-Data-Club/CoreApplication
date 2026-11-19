package middleware

import (
	"context"
	"errors"
	"io"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"

	"example/hello/internal/config"
)

type failedCounter struct{}

func TestQuestionBatchUsesBoundedImportBudgetOnly(t *testing.T) {
	for _, route := range []struct {
		path   string
		budget time.Duration
	}{
		{"/api/v1/quizzes/:quizId/questions/batch", 2 * time.Minute},
		{"/api/v1/quizzes/:quizId/questions", 15 * time.Second},
	} {
		t.Run(route.path, func(t *testing.T) {
			r := gin.New()
			r.Use(RequestBudget(1024, config.DefaultRequestLimits()))
			r.POST(route.path, func(c *gin.Context) {
				deadline, ok := c.Request.Context().Deadline()
				remaining := time.Until(deadline)
				if !ok || remaining > route.budget || remaining < route.budget-time.Second {
					t.Fatalf("unexpected deadline: %v", remaining)
				}
				c.Status(204)
			})
			path := strings.ReplaceAll(route.path, ":quizId", "117")
			r.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest("POST", path, nil))
		})
	}
}

func (failedCounter) IncrementWithExpiry(context.Context, string, time.Duration) (int64, error) {
	return 0, errors.New("redis offline")
}
func TestRateLimitFallsBackAndExpires(t *testing.T) {
	gin.SetMode(gin.TestMode)
	l := newLimiter(failedCounter{})
	now := time.Now()
	l.now = func() time.Time { return now }
	run := func() int {
		r := gin.New()
		r.GET("/", func(c *gin.Context) {
			if l.allow(c, "private-proxy-ip", 2, time.Minute) {
				c.Status(204)
			}
		})
		w := httptest.NewRecorder()
		r.ServeHTTP(w, httptest.NewRequest("GET", "/", nil))
		return w.Code
	}
	if run() != 204 || run() != 204 || run() != 429 {
		t.Fatal("Redis outage removed request limits")
	}
	now = now.Add(time.Minute)
	if run() != 204 {
		t.Fatal("fallback window did not expire")
	}
}
func TestRequestBudgetBoundsJSON(t *testing.T) {
	r := gin.New()
	r.Use(RequestBudget(1000, config.DefaultRequestLimits()))
	r.POST("/body", func(c *gin.Context) {
		_, err := io.ReadAll(c.Request.Body)
		if err != nil {
			c.Status(413)
		} else {
			c.Status(204)
		}
	})
	req := httptest.NewRequest("POST", "/body", strings.NewReader(strings.Repeat("x", (2<<20)+1)))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	if w.Code != 413 {
		t.Fatalf("large JSON status=%d", w.Code)
	}
}
func TestAdmissionRejectsWhenUploadSlotsFull(t *testing.T) {
	r := gin.New()
	budget := RequestBudget(1024, config.DefaultRequestLimits())
	r.Use(budget)
	entered := make(chan struct{}, 4)
	release := make(chan struct{})
	r.POST("/upload", func(c *gin.Context) { entered <- struct{}{}; <-release; c.Status(204) })
	done := make(chan struct{}, 4)
	for i := 0; i < 4; i++ {
		go func() {
			defer func() { done <- struct{}{} }()
			req := httptest.NewRequest("POST", "/upload", nil)
			req.Header.Set("Content-Type", "multipart/form-data; boundary=x")
			r.ServeHTTP(httptest.NewRecorder(), req)
		}()
	}
	for i := 0; i < 4; i++ {
		<-entered
	}
	req := httptest.NewRequest("POST", "/upload", nil)
	req.Header.Set("Content-Type", "multipart/form-data; boundary=x")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	close(release)
	for i := 0; i < 4; i++ {
		<-done
	}
	if w.Code != 503 {
		t.Fatalf("over-capacity status=%d", w.Code)
	}
}

func TestPerUserStreamLimitReleasesOnClose(t *testing.T) {
	r := gin.New()
	r.Use(func(c *gin.Context) { c.Set("user_id", int64(41)); c.Next() }, LimitStreamsPerUser(2))
	entered := make(chan struct{}, 2)
	release := make(chan struct{})
	r.GET("/stream", func(c *gin.Context) { entered <- struct{}{}; <-release; c.Status(204) })
	done := make(chan struct{}, 2)
	for i := 0; i < 2; i++ {
		go func() {
			defer func() { done <- struct{}{} }()
			r.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest("GET", "/stream", nil))
		}()
	}
	<-entered
	<-entered
	w := httptest.NewRecorder()
	r.ServeHTTP(w, httptest.NewRequest("GET", "/stream", nil))
	if w.Code != 429 {
		t.Errorf("third stream status=%d", w.Code)
	}
	close(release)
	<-done
	<-done
	w = httptest.NewRecorder()
	r.ServeHTTP(w, httptest.NewRequest("GET", "/stream", nil))
	if w.Code != 204 {
		t.Errorf("slot was not released: %d", w.Code)
	}
}
