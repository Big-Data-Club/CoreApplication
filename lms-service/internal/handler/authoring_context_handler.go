package handler

import (
	"net/http"
	"strconv"
	"strings"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"github.com/gin-gonic/gin"
)

// AuthoringSources resolves the authorized course/chapter/lesson scope.
// @Summary Resolve canonical authoring material for a course
// @Description Authorizes the owner, co-teacher or administrator. Empty ID lists select the course; invalid explicit IDs fail the request.
// @Tags courses
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param courseId path int true "Course ID"
// @Param request body service.AuthoringScope true "Chapter/lesson scope"
// @Success 200 {object} dto.SuccessResponse
// @Failure 403 {object} dto.ErrorResponse
// @Failure 422 {object} dto.ErrorResponse
// @Router /courses/{courseId}/authoring-context [post]
func (h *CourseHandler) AuthoringSources(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil || courseID <= 0 {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid course ID"))
		return
	}
	var scope service.AuthoringScope
	if err := c.ShouldBindJSON(&scope); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	role := getRoleFromContext(c)
	if c.GetString("user_email") == "system@bdc.internal" {
		role = "SERVICE"
	}
	sources, err := h.courseService.AuthoringSources(c.Request.Context(), courseID, c.GetInt64("user_id"), role, scope)
	if err != nil {
		status := http.StatusUnprocessableEntity
		if strings.Contains(err.Error(), "permission denied") {
			status = http.StatusForbidden
		}
		c.JSON(status, dto.NewErrorResponse("authoring_context", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(sources))
}
