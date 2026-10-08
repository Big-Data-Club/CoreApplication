package handler

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"example/hello/internal/dto"
	"example/hello/pkg/ai"
	"example/hello/pkg/kafka"
	"github.com/gin-gonic/gin"
)

// PersonalFlashcardHandler injects learner identity and verifies course access.
// Knowledge nodes are not part of this contract.
type flashcardCourseAccess interface {
	VerifyAccess(context.Context, int64, int64, string) error
}
type PersonalFlashcardHandler struct {
	client *ai.Client
	access flashcardCourseAccess
}

func NewPersonalFlashcardHandler(client *ai.Client, access flashcardCourseAccess) *PersonalFlashcardHandler {
	return &PersonalFlashcardHandler{client: client, access: access}
}

func (h *PersonalFlashcardHandler) Action(c *gin.Context) {
	studentID := c.GetInt64("user_id")
	if studentID <= 0 {
		c.AbortWithStatus(http.StatusUnauthorized)
		return
	}
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil || courseID <= 0 {
		c.AbortWithStatus(http.StatusBadRequest)
		return
	}
	if err := h.access.VerifyAccess(c.Request.Context(), studentID, courseID, c.GetString("user_role")); err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Bạn không có quyền truy cập khóa học này"))
		return
	}
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, 2<<20)
	var body struct {
		Action string                 `json:"action" binding:"required,oneof=list create_deck rename_deck delete_deck save_cards delete_card generate check job assign_deck"`
		Data   map[string]interface{} `json:"data"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", "Dữ liệu không hợp lệ"))
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 20*time.Second)
	defer cancel()
	result, err := h.client.PersonalFlashcardAction(ctx, studentID, courseID, body.Action, body.Data)
	if err != nil {
		status := http.StatusBadGateway
		if upstream, ok := err.(*ai.PersonalFlashcardError); ok {
			status = upstream.Status
		}
		c.JSON(status, dto.NewErrorResponse("flashcard_error", "Không thể xử lý flashcard. Hãy tải lại và thử lại."))
		return
	}
	if body.Action == "generate" || body.Action == "check" {
		if jobID, ok := result["job_id"].(string); ok {
			payload, _ := json.Marshal(map[string]string{"job_id": jobID})
			err = kafka.PublishEvent(ctx, "lms.ai.command", []byte(jobID), kafka.AICommandEvent{
				JobID: jobID, CourseID: courseID, CommandType: "PERSONAL_FLASHCARD", Payload: payload, CreatedAt: time.Now(),
			})
			if err != nil {
				_, _ = h.client.PersonalFlashcardAction(ctx, studentID, courseID, "queue_failed", map[string]interface{}{"job_id": jobID})
				c.JSON(http.StatusServiceUnavailable, dto.NewErrorResponse("queue_unavailable", "Chưa gửi được yêu cầu AI. Hãy thử lại."))
				return
			}
		}
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}
