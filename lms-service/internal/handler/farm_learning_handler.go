package handler

import (
	"crypto/subtle"
	"database/sql"
	"errors"
	"net/http"
	"strconv"

	"example/hello/internal/service"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

// FarmLearningHandler is internal-only: the response contains grading keys.
// It must never be mounted on a JWT or public browser route.
type FarmLearningHandler struct {
	service *service.FarmLearningService
	secret  string
}

func NewFarmLearningHandler(s *service.FarmLearningService, secret string) *FarmLearningHandler {
	return &FarmLearningHandler{s, secret}
}
func (h *FarmLearningHandler) Authenticate(c *gin.Context) {
	provided := c.GetHeader("X-API-Secret")
	if h.secret == "" || subtle.ConstantTimeCompare([]byte(provided), []byte(h.secret)) != 1 {
		c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}
	c.Next()
}
func (h *FarmLearningHandler) Question(c *gin.Context) {
	userID, err := strconv.ParseInt(c.Query("user_id"), 10, 64)
	if err != nil || userID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid user"})
		return
	}
	q, err := h.service.Question(c.Request.Context(), userID, c.Query("kind"), c.Query("exclude"))
	if errors.Is(err, sql.ErrNoRows) {
		c.JSON(http.StatusNotFound, gin.H{"error": "Chưa có câu hỏi hoặc flashcard trong khóa học đã tham gia."})
		return
	}
	if err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "LMS learning content unavailable"})
		return
	}
	c.JSON(http.StatusOK, q)
}
func (h *FarmLearningHandler) Attempt(c *gin.Context) {
	var body service.FarmAttempt
	if err := c.ShouldBindJSON(&body); err != nil || uuid.Validate(body.ChallengeID) != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid attempt"})
		return
	}
	if err := h.service.RecordAttempt(c.Request.Context(), body); err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Could not record attempt"})
		return
	}
	c.Status(http.StatusNoContent)
}
