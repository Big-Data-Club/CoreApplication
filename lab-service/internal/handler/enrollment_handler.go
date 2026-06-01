package handler

import (
	"net/http"
	"strconv"

	"lab-service/internal/dto"
	"lab-service/internal/repository"

	"github.com/gin-gonic/gin"
)

type EnrollmentHandler struct {
	enrollRepo *repository.EnrollmentRepository
}

func NewEnrollmentHandler(enrollRepo *repository.EnrollmentRepository) *EnrollmentHandler {
	return &EnrollmentHandler{enrollRepo: enrollRepo}
}

func (h *EnrollmentHandler) EnrollLab(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	userID := c.GetInt64("user_id")

	id, err := h.enrollRepo.Enroll(c.Request.Context(), labID, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("error", err.Error()))
		return
	}
	if id == 0 {
		c.JSON(http.StatusOK, dto.NewMessageResponse("Already enrolled"))
		return
	}
	c.JSON(http.StatusCreated, dto.NewSuccessResponse("Enrolled successfully", map[string]int64{"enrollment_id": id}))
}

func (h *EnrollmentHandler) GetLabLearners(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	status := c.Query("status")

	learners, err := h.enrollRepo.GetLabLearners(c.Request.Context(), labID, status)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("error", err.Error()))
		return
	}
	if learners == nil {
		learners = []map[string]interface{}{}
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(learners))
}

func (h *EnrollmentHandler) GetMyLabEnrollments(c *gin.Context) {
	userID := c.GetInt64("user_id")

	enrollments, err := h.enrollRepo.GetMyLabEnrollments(c.Request.Context(), userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("error", err.Error()))
		return
	}
	if enrollments == nil {
		enrollments = []map[string]interface{}{}
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(enrollments))
}

func (h *EnrollmentHandler) CancelEnrollment(c *gin.Context) {
	enrollmentID, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	userID := c.GetInt64("user_id")

	if err := h.enrollRepo.Cancel(c.Request.Context(), enrollmentID, userID); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Enrollment cancelled"))
}

func (h *EnrollmentHandler) BulkEnroll(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	var body struct {
		UserIDs []int64 `json:"user_ids" binding:"required"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	count, err := h.enrollRepo.BulkEnroll(c.Request.Context(), labID, body.UserIDs)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewSuccessResponse("Bulk enrollment done", map[string]int{"enrolled": count}))
}
