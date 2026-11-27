package handler

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"github.com/gin-gonic/gin"
)

type quizIndexService interface {
	QuizIndexAction(context.Context, int64, int64, string, string, service.QuizIndexRequest) (json.RawMessage, error)
	QuizIndexSource(context.Context, int64, int64, int64, bool) (interface{}, error)
}
type QuizIndexHandler struct{ service quizIndexService }

func NewQuizIndexHandler(s quizIndexService) *QuizIndexHandler { return &QuizIndexHandler{s} }

func (h *QuizIndexHandler) Action(action string) gin.HandlerFunc {
	return func(c *gin.Context) {
		id, err := strconv.ParseInt(c.Param("quizId"), 10, 64)
		user, ok := c.Get("user_id")
		uid, valid := user.(int64)
		if err != nil || id <= 0 {
			c.JSON(400, dto.NewErrorResponse("invalid_quiz", "Invalid quiz"))
			return
		}
		if !ok || !valid || uid <= 0 {
			c.JSON(401, dto.NewErrorResponse("unauthorized", "Authentication required"))
			return
		}
		var body service.QuizIndexRequest
		if action == "state" {
			body.Offset, _ = strconv.Atoi(c.DefaultQuery("offset", "0"))
		}
		if action != "state" {
			c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, 16384)
			if err = c.ShouldBindJSON(&body); err != nil {
				c.JSON(400, dto.NewErrorResponse("invalid_request", "Invalid request"))
				return
			}
		}
		if body.Offset < 0 || body.Offset > 100000 || len(body.Name) > 255 || len(body.Description) > 1500 || len(body.Query) > 2000 || action == "search" && strings.TrimSpace(body.Query) == "" || action == "link" && (body.QuestionID <= 0 || body.NodeID < 0 || body.NodeID == 0 && strings.TrimSpace(body.Name) == "" || len(body.SourceHash) != 32) {
			c.JSON(400, dto.NewErrorResponse("invalid_request", "Invalid search or node link"))
			return
		}
		timeout := 15 * time.Second
		if action == "suggest" || action == "link" {
			timeout = 60 * time.Second
		} else if action == "search" {
			timeout = 30 * time.Second
		}
		ctx, cancel := context.WithTimeout(c.Request.Context(), timeout)
		defer cancel()
		result, err := h.service.QuizIndexAction(ctx, id, uid, c.GetString("user_role"), action, body)
		if err != nil {
			if err == service.ErrQuizAccess {
				c.JSON(403, dto.NewErrorResponse("forbidden", "Cannot manage this quiz"))
				return
			}
			c.JSON(503, dto.NewErrorResponse("quiz_index_unavailable", "Quiz index unavailable or question changed; refresh and retry"))
			return
		}
		c.JSON(200, dto.NewDataResponse(result))
	}
}

func (h *QuizIndexHandler) Source(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("quizId"), 10, 64)
	uid, _ := strconv.ParseInt(c.Query("user_id"), 10, 64)
	after, _ := strconv.ParseInt(c.DefaultQuery("after", "0"), 10, 64)
	if err != nil || id <= 0 || uid <= 0 || after < 0 {
		c.JSON(400, dto.NewErrorResponse("invalid_request", "Invalid source request"))
		return
	}
	result, err := h.service.QuizIndexSource(c.Request.Context(), id, uid, after, c.Query("head") == "true")
	if err != nil {
		c.JSON(403, dto.NewErrorResponse("forbidden", "Cannot access quiz source"))
		return
	}
	c.JSON(200, result)
}
