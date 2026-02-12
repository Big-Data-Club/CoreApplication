package handler

import (
	"net/http"
	"strconv"

	"example/hello/internal/dto"
	"example/hello/internal/service"

	"github.com/gin-gonic/gin"
)

// GetMyQuizAttempts godoc
// @Summary Get my quiz attempts
// @Description Get all attempts by the current student for a specific quiz
// @Tags Quiz - Student
// @Accept json
// @Produce json
// @Param quizId path int true "Quiz ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=[]dto.QuizAttemptDTO} "List of quiz attempts"
// @Failure 400 {object} dto.ErrorResponse "Invalid quiz ID"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 500 {object} dto.ErrorResponse "Internal server error"
// @Router /quizzes/{quizId}/my-attempts [get]
func (h *QuizHandler) GetMyQuizAttempts(c *gin.Context) {
	quizID, err := strconv.ParseInt(c.Param("quizId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_quiz_id", "Invalid quiz ID"))
		return
	}

	userID, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "User not authenticated"))
		return
	}

	attempts, err := h.quizService.GetStudentAttempts(c.Request.Context(), quizID, userID.(int64))
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	// Convert to DTOs
	dtos := dto.ToQuizAttemptDTOList(attempts)

	c.JSON(http.StatusOK, dto.NewDataResponse(dtos))
}

// GetAttemptSummary godoc
// @Summary Get attempt summary
// @Description Get detailed summary of a quiz attempt including question breakdown, time, and score statistics
// @Tags Quiz - Student
// @Accept json
// @Produce json
// @Param attemptId path int true "Attempt ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.QuizAttemptSummaryDTO} "Attempt summary with detailed statistics"
// @Failure 400 {object} dto.ErrorResponse "Invalid attempt ID"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - not authorized to view this attempt"
// @Failure 404 {object} dto.ErrorResponse "Attempt not found"
// @Failure 500 {object} dto.ErrorResponse "Internal server error"
// @Router /attempts/{attemptId}/summary [get]
func (h *QuizHandler) GetAttemptSummary(c *gin.Context) {
	attemptID, err := strconv.ParseInt(c.Param("attemptId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_attempt_id", "Invalid attempt ID"))
		return
	}

	userID, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "User not authenticated"))
		return
	}

	summary, err := h.quizService.GetAttemptSummary(c.Request.Context(), attemptID, userID.(int64))
	if err != nil {
		if err.Error() == "attempt not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Attempt not found"))
			return
		}
		if err.Error() == "not authorized to view this attempt" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Not authorized to view this attempt"))
			return
		}
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	// Convert to DTO
	summaryDTO := dto.QuizAttemptSummaryDTO{
		Attempt:           dto.ToQuizAttemptDTO(summary.Attempt),
		QuestionBreakdown: convertQuestionResultsToDTO(summary.QuestionBreakdown),
		TimeBreakdown: dto.TimeBreakdownDTO{
			TotalSeconds:       summary.TimeBreakdown.TotalSeconds,
			TotalMinutes:       summary.TimeBreakdown.TotalMinutes,
			AveragePerQuestion: summary.TimeBreakdown.AveragePerQuestion,
			FormattedDuration:  summary.TimeBreakdown.FormattedDuration,
		},
		ScoreBreakdown: dto.ScoreBreakdownDTO{
			TotalPoints:    summary.ScoreBreakdown.TotalPoints,
			EarnedPoints:   summary.ScoreBreakdown.EarnedPoints,
			Percentage:     summary.ScoreBreakdown.Percentage,
			PassingScore:   summary.ScoreBreakdown.PassingScore,
			IsPassed:       summary.ScoreBreakdown.IsPassed,
			CorrectCount:   summary.ScoreBreakdown.CorrectCount,
			IncorrectCount: summary.ScoreBreakdown.IncorrectCount,
			UngradedCount:  summary.ScoreBreakdown.UngradedCount,
		},
		GradingStatus: dto.GradingStatusDTO{
			IsFullyGraded:       summary.GradingStatus.IsFullyGraded,
			PendingGradingCount: summary.GradingStatus.PendingGradingCount,
			IsProvisional:       summary.GradingStatus.IsProvisional,
		},
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(summaryDTO))
}

// Helper function to convert QuestionResult to DTO
func convertQuestionResultsToDTO(results []service.QuestionResult) []dto.QuestionResultDTO {
	dtos := make([]dto.QuestionResultDTO, len(results))
	for i, r := range results {
		dtos[i] = dto.QuestionResultDTO{
			QuestionID:       r.QuestionID,
			QuestionText:     r.QuestionText,
			QuestionType:     r.QuestionType,
			Points:           r.Points,
			PointsEarned:     r.PointsEarned,
			IsCorrect:        r.IsCorrect,
			TimeSpentSeconds: r.TimeSpentSeconds,
			AnsweredAt:       r.AnsweredAt,
		}
	}
	return dtos
}