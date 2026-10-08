package handler

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/ai"
	"example/hello/pkg/kafka"
	"example/hello/pkg/logger"
	"github.com/gin-gonic/gin"
)

// PersonalFlashcardHandler injects learner identity and verifies course access.
// Source text is resolved from published LMS content before calling AI.
type flashcardCourseAccess interface {
	VerifyAccess(context.Context, int64, int64, string) error
}
type PersonalFlashcardHandler struct {
	client  *ai.Client
	access  flashcardCourseAccess
	sources *service.StudySourceService
}

func NewPersonalFlashcardHandler(client *ai.Client, access flashcardCourseAccess, sources ...*service.StudySourceService) *PersonalFlashcardHandler {
	h := &PersonalFlashcardHandler{client: client, access: access}
	if len(sources) > 0 {
		h.sources = sources[0]
	}
	return h
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
		Action string                 `json:"action" binding:"required,oneof=list create_deck rename_deck delete_deck save_cards delete_card generate check job assign_deck generate_content quiz_content"`
		Data   map[string]interface{} `json:"data"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", "Dữ liệu không hợp lệ"))
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 20*time.Second)
	defer cancel()
	if body.Action == "generate_content" || body.Action == "quiz_content" {
		var input struct {
			ContentID int64  `json:"content_id"`
			LessonID  int64  `json:"lesson_id"`
			RequestID string `json:"request_id"`
			Count     int    `json:"count"`
			Language  string `json:"language"`
		}
		raw, _ := json.Marshal(body.Data)
		if json.Unmarshal(raw, &input) != nil || h.sources == nil {
			c.JSON(400, dto.NewErrorResponse("invalid_source", "Hãy chọn bài học để tạo câu hỏi"))
			return
		}
		source, sourceErr := h.sources.Resolve(ctx, courseID, input.ContentID, input.LessonID)
		if sourceErr != nil {
			c.JSON(404, dto.NewErrorResponse("source_not_found", sourceErr.Error()))
			return
		}
		if input.Count == 0 {
			input.Count = 5
		}
		if input.Language == "" {
			input.Language = "vi"
		}
		body.Data = map[string]interface{}{"source": source, "count": input.Count, "language": input.Language, "request_id": input.RequestID}
	}
	result, err := h.client.PersonalFlashcardAction(ctx, studentID, courseID, body.Action, body.Data)
	if err != nil {
		status := http.StatusBadGateway
		code, message := "flashcard_unavailable", "Chưa kết nối được kho thẻ. Hãy thử lại sau ít phút."
		if upstream, ok := err.(*ai.PersonalFlashcardError); ok {
			status = upstream.Status
			code, message = upstream.Code, upstream.Message
		}
		logger.WarnWithFields("Flashcard request failed", map[string]interface{}{"action": body.Action, "status": status, "code": code})
		c.JSON(status, dto.NewErrorResponse(code, message))
		return
	}
	if body.Action == "generate" || body.Action == "check" || body.Action == "generate_content" || body.Action == "quiz_content" {
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
