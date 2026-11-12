package handler

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"golang.org/x/sync/singleflight"
	"net/http"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"example/hello/internal/dto"
	"example/hello/pkg/kafka"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

type quizResultsService interface {
	AuthorizeQuizResults(context.Context, int64, int64, string) error
	GetQuizResults(context.Context, int64, int64, string, ...dto.QuizResultsQuery) (json.RawMessage, error)
	GetQuizResultRows(context.Context, int64, int64, string, dto.QuizResultsQuery) (json.RawMessage, error)
	GetTeacherAttemptResults(context.Context, int64, int64, int64, string) (interface{}, error)
}
type quizResultsCache interface {
	Get(context.Context, string) (string, error)
	Set(context.Context, string, interface{}, time.Duration) error
	SetNX(context.Context, string, interface{}, time.Duration) (bool, error)
}
type QuizResultsHandler struct {
	service quizResultsService
	cache   quizResultsCache
	reports singleflight.Group
	publish func(context.Context, string, []byte, interface{}) error
}

func NewQuizResultsHandler(s quizResultsService, cache quizResultsCache) *QuizResultsHandler {
	return &QuizResultsHandler{service: s, cache: cache, publish: kafka.PublishEvent}
}

func (h *QuizResultsHandler) scope(c *gin.Context) (int64, bool) {
	id, err := strconv.ParseInt(c.Param("quizId"), 10, 64)
	if err != nil || id <= 0 {
		c.JSON(400, dto.NewErrorResponse("invalid_quiz_id", "Invalid quiz ID"))
		return 0, false
	}
	user, ok := c.Get("user_id")
	if _, valid := user.(int64); !ok || !valid {
		c.JSON(401, dto.NewErrorResponse("unauthorized", "Authentication required"))
		return 0, false
	}
	role := c.GetString("user_role")
	err = h.service.AuthorizeQuizResults(c.Request.Context(), id, user.(int64), role)
	if err != nil {
		c.JSON(403, dto.NewErrorResponse("forbidden", "Cannot access quiz results"))
		return 0, false
	}
	return id, true
}

// Authorization runs before this shared cache; no learner data is cached by role.
func (h *QuizResultsHandler) cached(ctx context.Context, key string, fetch func(context.Context) (json.RawMessage, error)) (json.RawMessage, error) {
	result := h.reports.DoChan(key, func() (interface{}, error) {
		workCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
		defer cancel()
		if cached, err := h.cache.Get(workCtx, key); err == nil && json.Valid([]byte(cached)) {
			return json.RawMessage(cached), nil
		}
		report, err := fetch(workCtx)
		if err == nil {
			_ = h.cache.Set(workCtx, key, []byte(report), 15*time.Second)
		}
		return report, err
	})
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	case value := <-result:
		if value.Err != nil {
			return nil, value.Err
		}
		return value.Val.(json.RawMessage), nil
	}
}
func (h *QuizResultsHandler) loadReport(c *gin.Context, id int64, query dto.QuizResultsQuery) (json.RawMessage, error) {
	ctx := c.Request.Context()
	user := c.MustGet("user_id").(int64)
	role := c.GetString("user_role")
	global, err := h.cached(ctx, fmt.Sprintf("quiz_results:v3:%d:overview", id), func(ctx context.Context) (json.RawMessage, error) {
		return h.service.GetQuizResults(ctx, id, user, role)
	})
	if err != nil || query.Search == "" && query.AttemptPage == 1 && query.StudentPage == 1 {
		return global, err
	}
	key := fmt.Sprintf("quiz_results:v3:%d:%d:%d:%x", id, query.AttemptPage, query.StudentPage, sha256.Sum256([]byte(query.Search)))
	rows, err := h.cached(ctx, key, func(ctx context.Context) (json.RawMessage, error) {
		return h.service.GetQuizResultRows(ctx, id, user, role, query)
	})
	if err != nil {
		return nil, err
	}
	var merged, page map[string]json.RawMessage
	if err = json.Unmarshal(global, &merged); err != nil {
		return nil, err
	}
	if err = json.Unmarshal(rows, &page); err != nil {
		return nil, err
	}
	for key, value := range page {
		merged[key] = value
	}
	return json.Marshal(merged)
}
func (h *QuizResultsHandler) Get(c *gin.Context) {
	id, ok := h.scope(c)
	if !ok {
		return
	}
	query := dto.QuizResultsQuery{AttemptPage: 1, StudentPage: 1, Search: strings.TrimSpace(c.Query("search"))}
	for _, page := range []struct {
		name   string
		target *int
	}{{"attempt_page", &query.AttemptPage}, {"student_page", &query.StudentPage}} {
		if raw := c.Query(page.name); raw != "" {
			n, err := strconv.Atoi(raw)
			if err != nil || n < 1 || n > 100000 {
				c.JSON(400, dto.NewErrorResponse("invalid_page", "Invalid page"))
				return
			}
			*page.target = n
		}
	}
	if utf8.RuneCountInString(query.Search) > 100 {
		c.JSON(400, dto.NewErrorResponse("invalid_search", "Search is too long"))
		return
	}
	report, err := h.loadReport(c, id, query)
	if err != nil {
		c.JSON(503, dto.NewErrorResponse("unavailable", "Cannot load quiz results"))
		return
	}
	c.JSON(200, dto.NewDataResponse(report))
}
func (h *QuizResultsHandler) Answers(c *gin.Context) {
	id, ok := h.scope(c)
	if !ok {
		return
	}
	attempt, err := strconv.ParseInt(c.Param("attemptId"), 10, 64)
	if err != nil || attempt <= 0 {
		c.JSON(400, dto.NewErrorResponse("invalid_attempt_id", "Invalid attempt ID"))
		return
	}
	user, _ := c.Get("user_id")
	role := c.GetString("user_role")
	answers, err := h.service.GetTeacherAttemptResults(c.Request.Context(), id, attempt, user.(int64), role)
	if err != nil {
		c.JSON(404, dto.NewErrorResponse("not_found", "Attempt not found"))
		return
	}
	c.JSON(200, dto.NewDataResponse(answers))
}
func (h *QuizResultsHandler) Analyze(c *gin.Context) {
	id, ok := h.scope(c)
	if !ok {
		return
	}
	report, err := h.loadReport(c, id, dto.QuizResultsQuery{AttemptPage: 1, StudentPage: 1})
	if err != nil {
		c.JSON(503, dto.NewErrorResponse("unavailable", "Cannot load quiz results"))
		return
	}
	var snapshot struct {
		Summary      map[string]interface{}
		Questions    []map[string]interface{}
		Distribution []map[string]interface{}
	}
	if err := json.Unmarshal(report, &snapshot); err != nil {
		c.JSON(500, dto.NewErrorResponse("internal_error", "Invalid results"))
		return
	}
	graded, _ := snapshot.Summary["graded_attempts"].(float64)
	if graded < 1 {
		c.JSON(422, dto.NewErrorResponse("no_results", "Chưa có bài đã chấm để phân tích"))
		return
	}
	gateKey := fmt.Sprintf("quiz_insights_gate:%d", id)
	if existing, _ := h.cache.Get(c.Request.Context(), gateKey); existing != "" {
		c.JSON(202, dto.NewDataResponse(map[string]string{"job_id": existing, "status": "pending"}))
		return
	}
	job := "quiz-insights-" + uuid.NewString()
	ctx := c.Request.Context()
	owner, _ := json.Marshal(map[string]interface{}{"quiz_id": id})
	if err := h.cache.Set(ctx, "quiz_insights_owner:"+job, owner, 24*time.Hour); err != nil {
		c.JSON(503, dto.NewErrorResponse("unavailable", "Cannot track analysis"))
		return
	}
	initial, _ := json.Marshal(map[string]string{"job_id": job, "status": "pending"})
	if err := h.cache.Set(ctx, "ai_job:"+job, initial, 24*time.Hour); err != nil {
		c.JSON(503, dto.NewErrorResponse("unavailable", "Cannot track analysis"))
		return
	}
	gate := fmt.Sprintf("quiz_insights_gate:%d", id)
	acquired, gateErr := h.cache.SetNX(ctx, gate, job, 5*time.Minute)
	if gateErr != nil {
		c.JSON(503, dto.NewErrorResponse("unavailable", "Cannot queue analysis"))
		return
	}
	if !acquired {
		existing, _ := h.cache.Get(ctx, gate)
		if existing == "" {
			c.JSON(503, dto.NewErrorResponse("unavailable", "Analysis is being prepared"))
			return
		}
		c.JSON(202, dto.NewDataResponse(map[string]string{"job_id": existing, "status": "pending"}))
		return
	}

	event := kafka.AICommandEvent{JobID: job, CommandType: "ANALYZE_QUIZ_RESULTS", Payload: map[string]interface{}{"summary": snapshot.Summary, "questions": snapshot.Questions, "distribution": snapshot.Distribution}, CreatedAt: time.Now()}
	if err := h.publish(ctx, "lms.ai.command", []byte(job), event); err != nil {
		failed, _ := json.Marshal(map[string]string{"job_id": job, "status": "failed", "error": "Cannot queue analysis"})
		_ = h.cache.Set(ctx, "ai_job:"+job, failed, 24*time.Hour)
		_ = h.cache.Set(ctx, gate, job, 5*time.Second)
		c.JSON(503, dto.NewErrorResponse("queue_unavailable", "Cannot queue analysis"))
		return
	}
	c.JSON(http.StatusAccepted, dto.NewDataResponse(map[string]string{"job_id": job, "status": "pending"}))
}
func (h *QuizResultsHandler) Status(c *gin.Context) {
	id, ok := h.scope(c)
	if !ok {
		return
	}
	job := c.Param("jobId")
	owner, err := h.cache.Get(c.Request.Context(), "quiz_insights_owner:"+job)
	var scope struct {
		QuizID int64 `json:"quiz_id"`
	}
	if err != nil || json.Unmarshal([]byte(owner), &scope) != nil || scope.QuizID != id {
		c.JSON(404, dto.NewErrorResponse("not_found", "Analysis not found"))
		return
	}
	data, err := h.cache.Get(c.Request.Context(), "ai_job:"+job)
	if err != nil || !json.Valid([]byte(data)) {
		c.JSON(404, dto.NewErrorResponse("not_found", "Analysis expired"))
		return
	}
	c.JSON(200, dto.NewDataResponse(json.RawMessage(data)))
}
