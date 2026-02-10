package handler

import (
	"net/http"
	"strconv"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
)

type EnrollmentHandler struct {
	enrollmentService *service.EnrollmentService
}

func NewEnrollmentHandler(enrollmentService *service.EnrollmentService) *EnrollmentHandler {
	return &EnrollmentHandler{
		enrollmentService: enrollmentService,
	}
}

// EnrollCourse godoc
// @Summary Enroll in a course
// @Description Student enrolls in a course (status will be WAITING until teacher accepts)
// @Tags Enrollment
// @Accept json
// @Produce json
// @Param request body dto.EnrollCourseRequest true "Enrollment request"
// @Security BearerAuth
// @Success 201 {object} dto.SuccessResponse{data=dto.EnrollmentResponse} "Enrollment created"
// @Failure 400 {object} dto.ErrorResponse "Invalid request or already enrolled"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Router /enrollments [post]
func (h *EnrollmentHandler) EnrollCourse(c *gin.Context) {
	userID, _ := c.Get("user_id")

	var req dto.EnrollCourseRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	enrollment, err := h.enrollmentService.EnrollCourse(c.Request.Context(), req.CourseID, userID.(int64))
	if err != nil {
		logger.Error("Failed to enroll course", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("enrollment_failed", err.Error()))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(enrollment))
}

// GetMyEnrollments godoc
// @Summary Get my enrollments
// @Description Get all enrollments for the authenticated student, optionally filtered by status
// @Tags Enrollment
// @Accept json
// @Produce json
// @Param status query string false "Filter by status (WAITING, ACCEPTED, REJECTED)"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=[]dto.StudentEnrollmentResponse} "List of enrollments"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 500 {object} dto.ErrorResponse "Internal server error"
// @Router /enrollments/my [get]
func (h *EnrollmentHandler) GetMyEnrollments(c *gin.Context) {
	userID, _ := c.Get("user_id")

	status := c.DefaultQuery("status", "")

	enrollments, err := h.enrollmentService.GetMyEnrollments(c.Request.Context(), userID.(int64), status)
	if err != nil {
		logger.Error("Failed to get enrollments", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve enrollments"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(enrollments))
}

// GetCourseLearners godoc
// @Summary Get course learners
// @Description Get all learners enrolled in a course (only accessible by course creator or admin)
// @Tags Enrollment
// @Accept json
// @Produce json
// @Param courseId path int true "Course ID"
// @Param status query string false "Filter by status (WAITING, ACCEPTED, REJECTED)"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=[]dto.LearnerResponse} "List of learners"
// @Failure 400 {object} dto.ErrorResponse "Invalid course ID"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - not course creator"
// @Router /courses/{courseId}/learners [get]
func (h *EnrollmentHandler) GetCourseLearners(c *gin.Context) {
	userID, _ := c.Get("user_id")
	role, _ := c.Get("user_role")

	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_course_id", "Invalid course ID"))
		return
	}

	status := c.DefaultQuery("status", "")

	learners, err := h.enrollmentService.GetCourseLearners(c.Request.Context(), courseID, status, userID.(int64), role.(string))
	if err != nil {
		logger.Error("Failed to get course learners", err)
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(learners))
}

// AcceptEnrollment godoc
// @Summary Accept enrollment request
// @Description Accept a student's enrollment request (only accessible by course creator or admin)
// @Tags Enrollment
// @Accept json
// @Produce json
// @Param enrollmentId path int true "Enrollment ID"
// @Param request body object{course_id=int} true "Course ID for verification"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{message=string} "Enrollment accepted"
// @Failure 400 {object} dto.ErrorResponse "Invalid request"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - not course creator"
// @Router /enrollments/{enrollmentId}/accept [put]
func (h *EnrollmentHandler) AcceptEnrollment(c *gin.Context) {
	userID, _ := c.Get("user_id")
	role, _ := c.Get("user_role")

	enrollmentID, err := strconv.ParseInt(c.Param("enrollmentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_enrollment_id", "Invalid enrollment ID"))
		return
	}

	var req struct {
		CourseID int64 `json:"course_id" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", "Course ID is required"))
		return
	}

	err = h.enrollmentService.AcceptEnrollment(c.Request.Context(), enrollmentID, req.CourseID, userID.(int64), role.(string))
	if err != nil {
		logger.Error("Failed to accept enrollment", err)
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Enrollment accepted"))
}

// RejectEnrollment godoc
// @Summary Reject enrollment request
// @Description Reject a student's enrollment request (only accessible by course creator or admin)
// @Tags Enrollment
// @Accept json
// @Produce json
// @Param enrollmentId path int true "Enrollment ID"
// @Param request body object{course_id=int} true "Course ID for verification"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{message=string} "Enrollment rejected"
// @Failure 400 {object} dto.ErrorResponse "Invalid request"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - not course creator"
// @Router /enrollments/{enrollmentId}/reject [put]
func (h *EnrollmentHandler) RejectEnrollment(c *gin.Context) {
	userID, _ := c.Get("user_id")
	role, _ := c.Get("user_role")

	enrollmentID, err := strconv.ParseInt(c.Param("enrollmentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_enrollment_id", "Invalid enrollment ID"))
		return
	}

	var req struct {
		CourseID int64 `json:"course_id" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", "Course ID is required"))
		return
	}

	err = h.enrollmentService.RejectEnrollment(c.Request.Context(), enrollmentID, req.CourseID, userID.(int64), role.(string))
	if err != nil {
		logger.Error("Failed to reject enrollment", err)
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Enrollment rejected"))
}

// BulkEnroll godoc
// @Summary Bulk enroll students
// @Description Bulk enroll multiple students in a course with auto-accept (teacher/admin only)
// @Tags Enrollment
// @Accept json
// @Produce json
// @Param courseId path int true "Course ID"
// @Param request body dto.BulkEnrollmentRequest true "List of student IDs to enroll"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.BulkEnrollmentResponse} "Bulk enrollment result"
// @Failure 400 {object} dto.ErrorResponse "Invalid request"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Failure 403 {object} dto.ErrorResponse "Forbidden - teacher/admin only"
// @Router /courses/{courseId}/bulk-enroll [post]
func (h *EnrollmentHandler) BulkEnroll(c *gin.Context) {
	userID, _ := c.Get("user_id")
	role, _ := c.Get("user_role")

	// Only teachers and admins
	if role != "TEACHER" && role != "ADMIN" {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Only teachers can bulk enroll"))
		return
	}

	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_course_id", "Invalid course ID"))
		return
	}

	var req dto.BulkEnrollmentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	req.CourseID = courseID // Override with path param

	result := h.enrollmentService.BulkEnroll(c.Request.Context(), courseID, req.StudentID, userID.(int64), role.(string))

	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// CancelEnrollment godoc
// @Summary Cancel enrollment
// @Description Student cancels their pending enrollment request
// @Tags Enrollment
// @Accept json
// @Produce json
// @Param enrollmentId path int true "Enrollment ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{message=string} "Enrollment cancelled"
// @Failure 400 {object} dto.ErrorResponse "Invalid request or cannot cancel"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized"
// @Router /enrollments/{enrollmentId} [delete]
func (h *EnrollmentHandler) CancelEnrollment(c *gin.Context) {
	userID, _ := c.Get("user_id")

	enrollmentID, err := strconv.ParseInt(c.Param("enrollmentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_enrollment_id", "Invalid enrollment ID"))
		return
	}

	err = h.enrollmentService.CancelEnrollment(c.Request.Context(), enrollmentID, userID.(int64))
	if err != nil {
		logger.Error("Failed to cancel enrollment", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("cancel_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Enrollment cancelled"))
}