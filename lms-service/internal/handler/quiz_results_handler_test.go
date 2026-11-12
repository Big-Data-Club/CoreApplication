package handler

import (
	"context"
	"encoding/json"
	"errors"
	"example/hello/internal/dto"
	"github.com/gin-gonic/gin"
	"net/http/httptest"
	"sync"
	"testing"
	"time"
)

type resultServiceStub struct {
	denied bool
	reads  int
	report json.RawMessage
}

func (s *resultServiceStub) AuthorizeQuizResults(_ context.Context, quiz, user int64, role string) error {
	if s.denied || user != 7 || quiz != 42 {
		return errors.New("forbidden")
	}
	return nil
}
func (s *resultServiceStub) GetQuizResults(context.Context, int64, int64, string, ...dto.QuizResultsQuery) (json.RawMessage, error) {
	s.reads++
	if s.report != nil {
		return s.report, nil
	}
	return json.RawMessage(`{"quiz_id":42,"attempts":[],"questions":[]}`), nil
}
func (*resultServiceStub) GetTeacherAttemptResults(context.Context, int64, int64, int64, string) (interface{}, error) {
	return nil, errors.New("wrong quiz")
}

type resultCacheStub map[string]string

func (c resultCacheStub) Get(_ context.Context, key string) (string, error) { return c[key], nil }
func (c resultCacheStub) Set(_ context.Context, key string, value interface{}, _ time.Duration) error {
	c[key] = string(value.([]byte))
	return nil
}

func TestQuizResultsAuthorization(t *testing.T) {
	gin.SetMode(gin.TestMode)
	for _, tc := range []struct {
		name, path string
		user       bool
		denied     bool
		want       int
	}{
		{"teacher", "/42/results", true, false, 200},
		{"unauthenticated", "/42/results", false, false, 401},
		{"other teacher", "/42/results", true, true, 403},
		{"invalid id", "/bad/results", true, false, 400},
		{"negative id", "/-1/results", true, false, 400},
	} {
		t.Run(tc.name, func(t *testing.T) {
			svc := &resultServiceStub{denied: tc.denied}
			h := NewQuizResultsHandler(svc, resultCacheStub{})
			router := gin.New()
			router.Use(func(c *gin.Context) {
				if tc.user {
					c.Set("user_id", int64(7))
					c.Set("user_role", "TEACHER")
				}
			})
			router.GET("/:quizId/results", h.Get)
			w := httptest.NewRecorder()
			router.ServeHTTP(w, httptest.NewRequest("GET", tc.path, nil))
			if w.Code != tc.want {
				t.Fatalf("want %d got %d: %s", tc.want, w.Code, w.Body)
			}
			if tc.want != 200 && svc.reads != 0 {
				t.Fatal("unauthorized request read learner results")
			}
		})
	}
}

func TestQuizInsightsStatusChecksQuizScope(t *testing.T) {
	gin.SetMode(gin.TestMode)
	for _, tc := range []struct {
		scope string
		want  int
	}{{`{"quiz_id":42}`, 200}, {`{"quiz_id":99}`, 404}, {``, 404}} {
		svc := &resultServiceStub{}
		h := NewQuizResultsHandler(svc, resultCacheStub{"quiz_insights_owner:job": tc.scope, "ai_job:job": `{"status":"completed","result":{"summary":"report"}}`})
		router := gin.New()
		router.Use(func(c *gin.Context) { c.Set("user_id", int64(7)); c.Set("user_role", "TEACHER") })
		router.GET("/:quizId/results/insights/:jobId", h.Status)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, httptest.NewRequest("GET", "/42/results/insights/job", nil))
		if w.Code != tc.want {
			t.Fatalf("want %d got %d", tc.want, w.Code)
		}
		if svc.reads != 0 {
			t.Fatal("polling should authorize without reloading all results")
		}
	}
}

func TestTeacherAttemptDoesNotReturnOtherQuizAnswers(t *testing.T) {
	h := NewQuizResultsHandler(&resultServiceStub{}, resultCacheStub{})
	router := gin.New()
	router.Use(func(c *gin.Context) { c.Set("user_id", int64(7)); c.Set("user_role", "TEACHER") })
	router.GET("/:quizId/results/attempts/:attemptId", h.Answers)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, httptest.NewRequest("GET", "/42/results/attempts/55", nil))
	if w.Code != 404 {
		t.Fatalf("want 404 got %d", w.Code)
	}
}

func TestGenericJobPollingCannotExposeQuizInsights(t *testing.T) {
	h := NewAIHandler(nil, nil, nil, nil)
	router := gin.New()
	router.GET("/jobs/:jobId", h.GetJobStatus())
	w := httptest.NewRecorder()
	router.ServeHTTP(w, httptest.NewRequest("GET", "/jobs/quiz-insights-anything", nil))
	if w.Code != 403 {
		t.Fatalf("want 403 got %d", w.Code)
	}
}

func TestQuizAnalysisRequiresGradedSubmissions(t *testing.T) {
	h := NewQuizResultsHandler(&resultServiceStub{}, resultCacheStub{})
	router := gin.New()
	router.Use(func(c *gin.Context) { c.Set("user_id", int64(7)); c.Set("user_role", "TEACHER") })
	router.POST("/:quizId/results/insights", h.Analyze)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, httptest.NewRequest("POST", "/42/results/insights", nil))
	if w.Code != 422 {
		t.Fatalf("want 422 got %d", w.Code)
	}
}

func (c resultCacheStub) SetNX(ctx context.Context, key string, value interface{}, ttl time.Duration) (bool, error) {
	if c[key] != "" {
		return false, nil
	}
	c[key] = value.(string)
	return true, nil
}

func TestQuizResultsCacheDoesNotBypassAuthorization(t *testing.T) {
	svc := &resultServiceStub{}
	h := NewQuizResultsHandler(svc, resultCacheStub{})
	router := gin.New()
	router.Use(func(c *gin.Context) { c.Set("user_id", int64(7)); c.Set("user_role", "TEACHER") })
	router.GET("/:quizId/results", h.Get)
	for i := 0; i < 2; i++ {
		w := httptest.NewRecorder()
		router.ServeHTTP(w, httptest.NewRequest("GET", "/42/results", nil))
		if w.Code != 200 {
			t.Fatalf("request failed: %s", w.Body)
		}
	}
	if svc.reads != 1 {
		t.Fatalf("cache miss: read %d times", svc.reads)
	}
	svc.denied = true
	w := httptest.NewRecorder()
	router.ServeHTTP(w, httptest.NewRequest("GET", "/42/results", nil))
	if w.Code != 403 {
		t.Fatalf("cached results bypassed revoked permission: %d", w.Code)
	}
}

func TestQuizResultPagesAreValidated(t *testing.T) {
	h := NewQuizResultsHandler(&resultServiceStub{}, resultCacheStub{})
	router := gin.New()
	router.Use(func(c *gin.Context) { c.Set("user_id", int64(7)); c.Set("user_role", "TEACHER") })
	router.GET("/:quizId/results", h.Get)
	for _, query := range []string{"?attempt_page=0", "?student_page=-1", "?attempt_page=100001", "?student_page=bad"} {
		w := httptest.NewRecorder()
		router.ServeHTTP(w, httptest.NewRequest("GET", "/42/results"+query, nil))
		if w.Code != 400 {
			t.Fatalf("invalid page accepted: %s %d", query, w.Code)
		}
	}
}

func (s *resultServiceStub) GetQuizResultRows(context.Context, int64, int64, string, dto.QuizResultsQuery) (json.RawMessage, error) {
	return json.RawMessage(`{"attempts":[],"students":[],"attempts_total":0,"students_total":0,"attempt_page":2,"student_page":1,"page_size":50}`), nil
}

func TestQuizReportOverviewReusedAcrossDifferentPages(t *testing.T) {
	svc := &resultServiceStub{}
	h := NewQuizResultsHandler(svc, resultCacheStub{})
	router := gin.New()
	router.Use(func(c *gin.Context) { c.Set("user_id", int64(7)); c.Set("user_role", "TEACHER") })
	router.GET("/:quizId/results", h.Get)
	for _, suffix := range []string{"", "?attempt_page=2", "?search=test"} {
		w := httptest.NewRecorder()
		router.ServeHTTP(w, httptest.NewRequest("GET", "/42/results"+suffix, nil))
		if w.Code != 200 {
			t.Fatalf("request failed: %s", w.Body)
		}
	}
	if svc.reads != 1 {
		t.Fatalf("global aggregates recomputed for a page/search: %d", svc.reads)
	}
}

func TestConcurrentQuizReadersShareAggregateWork(t *testing.T) {
	svc := &resultServiceStub{}
	h := NewQuizResultsHandler(svc, resultCacheStub{})
	router := gin.New()
	router.Use(func(c *gin.Context) { c.Set("user_id", int64(7)); c.Set("user_role", "TEACHER") })
	router.GET("/:quizId/results", h.Get)
	var wait sync.WaitGroup
	for i := 0; i < 30; i++ {
		wait.Add(1)
		go func() {
			defer wait.Done()
			w := httptest.NewRecorder()
			router.ServeHTTP(w, httptest.NewRequest("GET", "/42/results", nil))
			if w.Code != 200 {
				t.Errorf("request failed: %d", w.Code)
			}
		}()
	}
	wait.Wait()
	if svc.reads != 1 {
		t.Fatalf("30 readers recomputed overview %d times", svc.reads)
	}
}

func TestQuizInsightsGateReusesJobAcrossLMSInstances(t *testing.T) {
	svc := &resultServiceStub{report: json.RawMessage(`{"summary":{"graded_attempts":1000},"questions":[],"distribution":[]}`)}
	shared := resultCacheStub{}
	queued := 0
	var jobs []string
	for i := 0; i < 2; i++ {
		h := NewQuizResultsHandler(svc, shared)
		h.publish = func(context.Context, string, []byte, interface{}) error { queued++; return nil }
		router := gin.New()
		router.Use(func(c *gin.Context) { c.Set("user_id", int64(7)); c.Set("user_role", "TEACHER") })
		router.POST("/:quizId/results/insights", h.Analyze)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, httptest.NewRequest("POST", "/42/results/insights", nil))
		if w.Code != 202 {
			t.Fatalf("analysis failed: %s", w.Body)
		}
		var body struct {
			Data struct {
				JobID string `json:"job_id"`
			}
		}
		if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
			t.Fatal(err)
		}
		jobs = append(jobs, body.Data.JobID)
	}
	if queued != 1 || jobs[0] == "" || jobs[0] != jobs[1] {
		t.Fatalf("duplicate model jobs created: queued=%d jobs=%v", queued, jobs)
	}
}
