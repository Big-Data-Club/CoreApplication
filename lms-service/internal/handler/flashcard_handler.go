package handler

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"
)

type FlashcardHandler struct {
	flashcardService *service.FlashcardService
	enrollmentSvc    *service.EnrollmentService
}

func NewFlashcardHandler(flashcardService *service.FlashcardService, enrollmentSvc *service.EnrollmentService) *FlashcardHandler {
	return &FlashcardHandler{
		flashcardService: flashcardService,
		enrollmentSvc:    enrollmentSvc,
	}
}

// GenerateFlashcards POST /api/v1/courses/:courseId/flashcards/generate or POST /api/v1/courses/:courseId/nodes/:nodeId/flashcards/generate
func (h *FlashcardHandler) GenerateFlashcards(c *gin.Context) {
	studentID := c.MustGet("user_id").(int64)
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)
	
	var nodeID *int64
	if nodeIDStr := c.Param("nodeId"); nodeIDStr != "" {
		id, _ := strconv.ParseInt(nodeIDStr, 10, 64)
		nodeID = &id
	}

	var req dto.GenerateFlashcardsRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	// Verify course access
	userRole := c.MustGet("user_role").(string)
	if err := h.enrollmentSvc.VerifyAccess(c.Request.Context(), studentID, courseID, userRole); err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Bạn không có quyền truy cập khóa học này"))
		return
	}

	results, err := h.flashcardService.GenerateFlashcards(c.Request.Context(), studentID, courseID, nodeID, req)
	if err != nil {
		logger.Error("Failed to generate flashcards", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(results))
}

// ListDueFlashcards GET /api/v1/courses/:courseId/flashcards/due
func (h *FlashcardHandler) ListDueFlashcards(c *gin.Context) {
	studentID := c.MustGet("user_id").(int64)
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)

	// Verify course access
	userRole := c.MustGet("user_role").(string)
	if err := h.enrollmentSvc.VerifyAccess(c.Request.Context(), studentID, courseID, userRole); err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Bạn không có quyền truy cập khóa học này"))
		return
	}

	results, err := h.flashcardService.ListDueFlashcards(c.Request.Context(), studentID, courseID)
	if err != nil {
		logger.Error("Failed to list due flashcards", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(results))
}

// ReviewFlashcard POST /api/v1/flashcards/:flashcardId/review
func (h *FlashcardHandler) ReviewFlashcard(c *gin.Context) {
	studentID := c.MustGet("user_id").(int64)
	flashcardID, _ := strconv.ParseInt(c.Param("flashcardId"), 10, 64)

	var req dto.ReviewFlashcardRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	result, err := h.flashcardService.ReviewFlashcard(c.Request.Context(), studentID, flashcardID, req)
	if err != nil {
		logger.Error("Failed to review flashcard", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// ListFlashcards GET /api/v1/courses/:courseId/flashcards?nodeId=&lessonId=
func (h *FlashcardHandler) ListFlashcards(c *gin.Context) {
	studentID := c.MustGet("user_id").(int64)
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_course_id", "Invalid course ID"))
		return
	}
	
	var nodeID *int64
	if nodeIDStr := c.Query("nodeId"); nodeIDStr != "" {
		if id, err := strconv.ParseInt(nodeIDStr, 10, 64); err == nil {
			nodeID = &id
		}
	} else if nodeIDStr := c.Param("nodeId"); nodeIDStr != "" {
		if id, err := strconv.ParseInt(nodeIDStr, 10, 64); err == nil {
			nodeID = &id
		}
	}

	var lessonID *int64
	if lessonIDStr := c.Query("lessonId"); lessonIDStr != "" {
		if id, err := strconv.ParseInt(lessonIDStr, 10, 64); err == nil {
			lessonID = &id
		}
	}

	// Verify course access
	userRole := c.MustGet("user_role").(string)
	if err := h.enrollmentSvc.VerifyAccess(c.Request.Context(), studentID, courseID, userRole); err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Bạn không có quyền truy cập khóa học này"))
		return
	}

	var contentID *int64
	if idStr := c.Query("contentId"); idStr != "" {
		id, _ := strconv.ParseInt(idStr, 10, 64)
		contentID = &id
	}

	results, err := h.flashcardService.ListFlashcards(c.Request.Context(), studentID, courseID, nodeID, lessonID, contentID)
	if err != nil {
		logger.Error("Failed to list flashcards", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(results))
}

// BulkSaveFlashcards POST /api/v1/courses/:courseId/flashcards/bulk-save
func (h *FlashcardHandler) BulkSaveFlashcards(c *gin.Context) {
	studentID := c.MustGet("user_id").(int64)
	courseID, _ := strconv.ParseInt(c.Param("courseId"), 10, 64)

	var req dto.BulkSaveFlashcardsRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	// Verify course access
	userRole := c.MustGet("user_role").(string)
	if err := h.enrollmentSvc.VerifyAccess(c.Request.Context(), studentID, courseID, userRole); err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Bạn không có quyền truy cập khóa học này"))
		return
	}

	results, err := h.flashcardService.BulkSaveFlashcards(c.Request.Context(), studentID, courseID, req)
	if err != nil {
		logger.Error("Failed to bulk save flashcards", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(results))
}
