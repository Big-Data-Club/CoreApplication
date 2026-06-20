package handler

import (
	"net/http"
	"strconv"
	"strings"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
)

type CoTeacherHandler struct {
	courseService *service.CourseService
}

func NewCoTeacherHandler(courseService *service.CourseService) *CoTeacherHandler {
	return &CoTeacherHandler{
		courseService: courseService,
	}
}

// AddCoTeacher adds a co-teacher to a course
// @Summary Add a co-teacher to a course
// @Description Add a co-teacher to a course (owner or admin only)
// @Tags co-teachers
// @Accept json
// @Produce json
// @Param courseId path int true "Course ID"
// @Param request body dto.AddCoTeacherRequest true "Add co-teacher request"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse
// @Failure 400 {object} dto.ErrorResponse
// @Failure 401 {object} dto.ErrorResponse
// @Failure 403 {object} dto.ErrorResponse
// @Failure 404 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /courses/{courseId}/co-teachers [post]
func (h *CoTeacherHandler) AddCoTeacher(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_course_id", "Invalid course ID"))
		return
	}

	var req dto.AddCoTeacherRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}

	actorID := c.GetInt64("user_id")
	role := getRoleFromContext(c)

	err = h.courseService.AddCoTeacher(c.Request.Context(), courseID, actorID, role, &req)
	if err != nil {
		if strings.Contains(err.Error(), "unauthorized") || strings.Contains(err.Error(), "forbidden") {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		if strings.Contains(err.Error(), "not found") {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", err.Error()))
			return
		}
		logger.Error("Failed to add co-teacher", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Co-teacher added successfully"))
}

// RemoveCoTeacher removes a co-teacher from a course
// @Summary Remove a co-teacher from a course
// @Description Remove a co-teacher from a course (owner or admin only)
// @Tags co-teachers
// @Accept json
// @Produce json
// @Param courseId path int true "Course ID"
// @Param userId path int true "User ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse
// @Failure 400 {object} dto.ErrorResponse
// @Failure 401 {object} dto.ErrorResponse
// @Failure 403 {object} dto.ErrorResponse
// @Failure 404 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /courses/{courseId}/co-teachers/{userId} [delete]
func (h *CoTeacherHandler) RemoveCoTeacher(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_course_id", "Invalid course ID"))
		return
	}

	targetUserID, err := strconv.ParseInt(c.Param("userId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_user_id", "Invalid user ID"))
		return
	}

	actorID := c.GetInt64("user_id")
	role := getRoleFromContext(c)

	err = h.courseService.RemoveCoTeacher(c.Request.Context(), courseID, targetUserID, actorID, role)
	if err != nil {
		if strings.Contains(err.Error(), "unauthorized") || strings.Contains(err.Error(), "forbidden") {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		if strings.Contains(err.Error(), "not found") {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", err.Error()))
			return
		}
		logger.Error("Failed to remove co-teacher", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Co-teacher removed successfully"))
}

// ListCoTeachers lists all co-teachers of a course
// @Summary List co-teachers of a course
// @Description List co-teachers of a course (accessible to authenticated users)
// @Tags co-teachers
// @Accept json
// @Produce json
// @Param courseId path int true "Course ID"
// @Security BearerAuth
// @Success 200 {array} dto.CoTeacherResponse
// @Failure 400 {object} dto.ErrorResponse
// @Failure 401 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /courses/{courseId}/co-teachers [get]
func (h *CoTeacherHandler) ListCoTeachers(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_course_id", "Invalid course ID"))
		return
	}

	actorID := c.GetInt64("user_id")
	role := getRoleFromContext(c)

	coTeachers, err := h.courseService.ListCoTeachers(c.Request.Context(), courseID, actorID, role)
	if err != nil {
		logger.Error("Failed to list co-teachers", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(coTeachers))
}
