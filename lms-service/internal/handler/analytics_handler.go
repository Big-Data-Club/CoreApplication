package handler

import (
	"net/http"
	"strconv"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/ai"

	"github.com/gin-gonic/gin"
)

type AnalyticsHandler struct {
	analyticsService *service.AnalyticsService
	aiClient         *ai.Client // thêm để gọi AI service cho weakness/flashcard stats
}

func NewAnalyticsHandler(analyticsService *service.AnalyticsService, aiClient *ai.Client) *AnalyticsHandler {
	return &AnalyticsHandler{
		analyticsService: analyticsService,
		aiClient:         aiClient,
	}
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

func getCourseIDParam(c *gin.Context) (int64, bool) {
	id, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_course_id", "Invalid course ID"))
		return 0, false
	}
	return id, true
}

func getQuizIDParam(c *gin.Context) (int64, bool) {
	id, err := strconv.ParseInt(c.Param("quizId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_quiz_id", "Invalid quiz ID"))
		return 0, false
	}
	return id, true
}

// ─── Teacher endpoints ────────────────────────────────────────────────────────

func (h *AnalyticsHandler) GetCourseQuizAnalytics(c *gin.Context) {
	courseID, ok := getCourseIDParam(c)
	if !ok {
		return
	}

	userID := c.MustGet("user_id").(int64)
	userRole := c.MustGet("user_role").(string)

	if err := h.analyticsService.VerifyCourseOwnership(c.Request.Context(), courseID, userID, userRole); err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
		return
	}

	data, err := h.analyticsService.GetCourseQuizAnalytics(c.Request.Context(), courseID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve quiz analytics"))
		return
	}

	c.JSON(http.StatusOK, data)
}

func (h *AnalyticsHandler) GetQuizAllAttempts(c *gin.Context) {
	quizID, ok := getQuizIDParam(c)
	if !ok {
		return
	}

	userID := c.MustGet("user_id").(int64)
	userRole := c.MustGet("user_role").(string)

	if err := h.analyticsService.VerifyQuizCourseOwnership(c.Request.Context(), quizID, userID, userRole); err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
		return
	}

	data, err := h.analyticsService.GetQuizAllAttempts(c.Request.Context(), quizID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve attempts"))
		return
	}

	c.JSON(http.StatusOK, data)
}

func (h *AnalyticsHandler) GetQuizWrongAnswerStats(c *gin.Context) {
	quizID, ok := getQuizIDParam(c)
	if !ok {
		return
	}

	userID := c.MustGet("user_id").(int64)
	userRole := c.MustGet("user_role").(string)

	if err := h.analyticsService.VerifyQuizCourseOwnership(c.Request.Context(), quizID, userID, userRole); err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
		return
	}

	data, err := h.analyticsService.GetQuizWrongAnswerStats(c.Request.Context(), quizID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve wrong answer stats"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(data))
}

func (h *AnalyticsHandler) GetStudentProgressOverview(c *gin.Context) {
	courseID, ok := getCourseIDParam(c)
	if !ok {
		return
	}

	userID := c.MustGet("user_id").(int64)
	userRole := c.MustGet("user_role").(string)

	if err := h.analyticsService.VerifyCourseOwnership(c.Request.Context(), courseID, userID, userRole); err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
		return
	}

	data, err := h.analyticsService.GetCourseStudentProgressOverview(c.Request.Context(), courseID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve student progress"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(data))
}

func (h *AnalyticsHandler) GetTeacherDashboardSummary(c *gin.Context) {
	userID := c.MustGet("user_id").(int64)
	userRole := c.MustGet("user_role").(string)

	if userRole != "TEACHER" && userRole != "ADMIN" {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Only teachers or admins can view dashboard summary"))
		return
	}

	data, err := h.analyticsService.GetTeacherDashboardSummary(c.Request.Context(), userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(data))
}


// ─── Student endpoints ─────────────────────────────────────────────────────────

func (h *AnalyticsHandler) GetMyQuizScores(c *gin.Context) {
	courseID, ok := getCourseIDParam(c)
	if !ok {
		return
	}

	userID := c.MustGet("user_id").(int64)

	data, err := h.analyticsService.GetMyQuizScores(c.Request.Context(), courseID, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve quiz scores"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(data))
}

// GetStudentWeaknesses godoc
// Gọi AI service để lấy dữ liệu weakness - không query trực tiếp AI DB.
// Đây là pattern loose coupling: LMS không biết schema AI DB.
func (h *AnalyticsHandler) GetStudentWeaknesses(c *gin.Context) {
	courseID, ok := getCourseIDParam(c)
	if !ok {
		return
	}
	userID := c.MustGet("user_id").(int64)

	// Delegate to service which handles AI client calls and consistent DTO mapping
	data, err := h.analyticsService.GetCourseStudentWeaknesses(c.Request.Context(), courseID, userID)
	if err != nil {
		// Graceful degradation: return empty overview instead of 500
		c.JSON(http.StatusOK, dto.NewDataResponse(&dto.StudentWeaknessOverview{
			TotalWrongPercent: 0,
			WeakNodes:         []dto.WeakNode{},
		}))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(data))
}

// GetFlashcardStats godoc
// Lấy SM-2 stats từ LMS DB (flashcard_repetitions đã migrate về LMS DB).
func (h *AnalyticsHandler) GetFlashcardStats(c *gin.Context) {
	courseID, ok := getCourseIDParam(c)
	if !ok {
		return
	}
	userID := c.MustGet("user_id").(int64)

	data, err := h.analyticsService.GetFlashcardStats(c.Request.Context(), courseID, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve flashcard stats"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(data))
}

func (h *AnalyticsHandler) GetStudentAnalyticsSummary(c *gin.Context) {
	courseID, ok := getCourseIDParam(c)
	if !ok {
		return
	}
	userID := c.MustGet("user_id").(int64)

	data, err := h.analyticsService.GetStudentAnalyticsSummary(c.Request.Context(), courseID, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(data))
}