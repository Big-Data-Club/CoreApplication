package handler

import (
	"net/http"

	"example/hello/internal/dto"
	"example/hello/pkg/ai"

	"github.com/gin-gonic/gin"
)

// CompetencyAIHandler is the authenticated BFF boundary for draft competency
// suggestions. It never persists AI output; a later explicit save operation is
// required after the admin or teacher has reviewed the draft.
type CompetencyAIHandler struct{ ai *ai.Client }

func NewCompetencyAIHandler(client *ai.Client) *CompetencyAIHandler {
	return &CompetencyAIHandler{ai: client}
}

func (h *CompetencyAIHandler) Suggest(c *gin.Context) {
	role := getRoleFromContext(c)
	if role != "ADMIN" && role != "TEACHER" {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Chỉ quản trị viên hoặc giảng viên có thể tạo bản nháp năng lực"))
		return
	}
	var body struct {
		Title           string `json:"title" binding:"required,min=3,max=255"`
		Subject         string `json:"subject" binding:"max=100"`
		Audience        string `json:"audience" binding:"max=255"`
		Language        string `json:"language" binding:"omitempty,max=10"`
		SourceText      string `json:"source_text" binding:"omitempty,max=12000"`
		MaxCompetencies int    `json:"max_competencies" binding:"omitempty,min=3,max=20"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	if body.Language == "" {
		body.Language = "vi"
	}
	if body.MaxCompetencies == 0 {
		body.MaxCompetencies = 8
	}
	result, err := h.ai.SuggestCompetencies(c.Request.Context(), map[string]interface{}{
		"title": body.Title, "subject": body.Subject, "audience": body.Audience,
		"language": body.Language, "source_text": body.SourceText, "max_competencies": body.MaxCompetencies,
	})
	if err != nil {
		c.JSON(http.StatusBadGateway, dto.NewErrorResponse("ai_error", "Không thể tạo bản nháp năng lực: "+err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}
