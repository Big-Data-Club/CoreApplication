package handler

import (
	"database/sql"
	"net/http"
	"strconv"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
)

type CourseHandler struct {
	courseService *service.CourseService
}

func NewCourseHandler(courseService *service.CourseService) *CourseHandler {
	return &CourseHandler{
		courseService: courseService,
	}
}

// CreateCourse creates a new course
// @Summary Create a course
// @Description Create a new course (Teacher/Admin only)
// @Tags courses
// @Accept json
// @Produce json
// @Param course body dto.CreateCourseRequest true "Course data"
// @Security BearerAuth
// @Success 201 {object} dto.CourseResponse
// @Failure 400 {object} dto.ErrorResponse
// @Failure 401 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /courses [post]
func (h *CourseHandler) CreateCourse(c *gin.Context) {
	var req dto.CreateCourseRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}

	userID := c.GetInt64("user_id")

	course, err := h.courseService.CreateCourse(c.Request.Context(), &req, userID)
	if err != nil {
		logger.Error("Failed to create course", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to create course"))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(course))
}

// GetCourse retrieves a course by ID
// @Summary Get a course
// @Description Get course details by ID
// @Tags courses
// @Accept json
// @Produce json
// @Param courseId path int true "Course ID"
// @Security BearerAuth
// @Success 200 {object} dto.CourseResponse
// @Failure 404 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /courses/{courseId} [get]
func (h *CourseHandler) GetCourse(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid course ID"))
		return
	}

	userID := c.GetInt64("user_id")
	role := c.GetString("user_role")

	course, err := h.courseService.GetCourse(c.Request.Context(), courseID, userID, role)
	if err != nil {
		if err == sql.ErrNoRows || err.Error() == "course not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Course not found"))
			return
		}
		if err.Error() == "unauthorized to view this course" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to get course", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve course"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(course))
}

// UpdateCourse updates a course
// @Summary Update a course
// @Description Update course details (Owner/Admin only)
// @Tags courses
// @Accept json
// @Produce json
// @Param courseId path int true "Course ID"
// @Param course body dto.UpdateCourseRequest true "Course data"
// @Security BearerAuth
// @Success 200 {object} dto.MessageResponse
// @Failure 400 {object} dto.ErrorResponse
// @Failure 403 {object} dto.ErrorResponse
// @Failure 404 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /courses/{courseId} [put]
func (h *CourseHandler) UpdateCourse(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid course ID"))
		return
	}

	var req dto.UpdateCourseRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}

	userID := c.GetInt64("user_id")
	role := c.GetString("user_role")

	err = h.courseService.UpdateCourse(c.Request.Context(), courseID, &req, userID, role)
	if err != nil {
		if err == sql.ErrNoRows || err.Error() == "course not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Course not found"))
			return
		}
		if err.Error() == "unauthorized to update this course" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to update course", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to update course"))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Course updated successfully"))
}

// DeleteCourse deletes a course
// @Summary Delete a course
// @Description Delete a course (Admin only)
// @Tags courses
// @Accept json
// @Produce json
// @Param courseId path int true "Course ID"
// @Security BearerAuth
// @Success 200 {object} dto.MessageResponse
// @Failure 403 {object} dto.ErrorResponse
// @Failure 404 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /courses/{courseId} [delete]
func (h *CourseHandler) DeleteCourse(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid course ID"))
		return
	}

	userID := c.GetInt64("user_id")
	role := c.GetString("user_role")

	err = h.courseService.DeleteCourse(c.Request.Context(), courseID, userID, role)
	if err != nil {
		if err == sql.ErrNoRows || err.Error() == "course not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Course not found"))
			return
		}
		if err.Error() == "unauthorized to delete this course" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to delete course", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to delete course"))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Course deleted successfully"))
}

// PublishCourse publishes a course
// @Summary Publish a course
// @Description Publish a course (Owner/Admin only)
// @Tags courses
// @Accept json
// @Produce json
// @Param courseId path int true "Course ID"
// @Security BearerAuth
// @Success 200 {object} dto.MessageResponse
// @Failure 403 {object} dto.ErrorResponse
// @Failure 404 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /courses/{courseId}/publish [post]
func (h *CourseHandler) PublishCourse(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid course ID"))
		return
	}

	userID := c.GetInt64("user_id")
	role := c.GetString("user_role")

	err = h.courseService.PublishCourse(c.Request.Context(), courseID, userID, role)
	if err != nil {
		if err == sql.ErrNoRows || err.Error() == "course not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Course not found"))
			return
		}
		if err.Error() == "unauthorized to publish this course" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to publish course", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to publish course"))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Course published successfully"))
}

// ListMyCourses lists courses created by the authenticated user
// @Summary List my courses
// @Description List all courses created by the authenticated user
// @Tags courses
// @Accept json
// @Produce json
// @Security BearerAuth
// @Success 200 {array} dto.CourseResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /courses/my [get]
func (h *CourseHandler) ListMyCourses(c *gin.Context) {
	userID := c.GetInt64("user_id")

	courses, err := h.courseService.ListMyCourses(c.Request.Context(), userID)
	if err != nil {
		logger.Error("Failed to list courses", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve courses"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(courses))
}

// ListPublishedCourses lists all published courses
// @Summary List published courses
// @Description List all published courses
// @Tags courses
// @Accept json
// @Produce json
// @Security BearerAuth
// @Success 200 {array} dto.CourseResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /courses [get]
func (h *CourseHandler) ListPublishedCourses(c *gin.Context) {
	courses, err := h.courseService.ListPublishedCourses(c.Request.Context())
	if err != nil {
		logger.Error("Failed to list published courses", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve courses"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(courses))
}

// ===== SECTION HANDLERS =====

// CreateSection creates a new section in a course
// @Summary Create a section
// @Description Create a new section in a course (Owner/Admin only)
// @Tags sections
// @Accept json
// @Produce json
// @Param courseId path int true "Course ID"
// @Param section body dto.CreateSectionRequest true "Section data"
// @Security BearerAuth
// @Success 201 {object} dto.SectionResponse
// @Failure 400 {object} dto.ErrorResponse
// @Failure 403 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /courses/{courseId}/sections [post]
func (h *CourseHandler) CreateSection(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid course ID"))
		return
	}

	var req dto.CreateSectionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}

	userID := c.GetInt64("user_id")
	role := c.GetString("user_role")

	section, err := h.courseService.CreateSection(c.Request.Context(), courseID, &req, userID, role)
	if err != nil {
		if err.Error() == "course not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Course not found"))
			return
		}
		if err.Error() == "unauthorized to create section in this course" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to create section", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to create section"))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(section))
}

// GetSection retrieves a section by ID
// @Summary Get a section
// @Description Get section details by ID
// @Tags sections
// @Accept json
// @Produce json
// @Param sectionId path int true "Section ID"
// @Security BearerAuth
// @Success 200 {object} dto.SectionResponse
// @Failure 404 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /sections/{sectionId} [get]
func (h *CourseHandler) GetSection(c *gin.Context) {
	sectionID, err := strconv.ParseInt(c.Param("sectionId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid section ID"))
		return
	}

	userID := c.GetInt64("user_id")
	role := c.GetString("user_role")

	section, err := h.courseService.GetSection(c.Request.Context(), sectionID, userID, role)
	if err != nil {
		if err.Error() == "section not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Section not found"))
			return
		}
		if err.Error() == "unauthorized to view this section" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to get section", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve section"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(section))
}

// ListSections lists all sections in a course
// @Summary List sections
// @Description List all sections in a course
// @Tags sections
// @Accept json
// @Produce json
// @Param courseId path int true "Course ID"
// @Security BearerAuth
// @Success 200 {array} dto.SectionResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /courses/{courseId}/sections [get]
func (h *CourseHandler) ListSections(c *gin.Context) {
	courseID, err := strconv.ParseInt(c.Param("courseId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid course ID"))
		return
	}

	userID := c.GetInt64("user_id")
	role := c.GetString("user_role")

	sections, err := h.courseService.ListSections(c.Request.Context(), courseID, userID, role)
	if err != nil {
		if err.Error() == "course not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Course not found"))
			return
		}
		logger.Error("Failed to list sections", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve sections"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(sections))
}

// UpdateSection updates a section
// @Summary Update a section
// @Description Update section details (Owner/Admin only)
// @Tags sections
// @Accept json
// @Produce json
// @Param sectionId path int true "Section ID"
// @Param section body dto.UpdateSectionRequest true "Section data"
// @Security BearerAuth
// @Success 200 {object} dto.MessageResponse
// @Failure 400 {object} dto.ErrorResponse
// @Failure 403 {object} dto.ErrorResponse
// @Failure 404 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /sections/{sectionId} [put]
func (h *CourseHandler) UpdateSection(c *gin.Context) {
	sectionID, err := strconv.ParseInt(c.Param("sectionId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid section ID"))
		return
	}

	var req dto.UpdateSectionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}

	userID := c.GetInt64("user_id")
	role := c.GetString("user_role")

	err = h.courseService.UpdateSection(c.Request.Context(), sectionID, &req, userID, role)
	if err != nil {
		if err.Error() == "section not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Section not found"))
			return
		}
		if err.Error() == "unauthorized to update this section" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to update section", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to update section"))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Section updated successfully"))
}

// DeleteSection deletes a section
// @Summary Delete a section
// @Description Delete a section (Owner/Admin only)
// @Tags sections
// @Accept json
// @Produce json
// @Param sectionId path int true "Section ID"
// @Security BearerAuth
// @Success 200 {object} dto.MessageResponse
// @Failure 403 {object} dto.ErrorResponse
// @Failure 404 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /sections/{sectionId} [delete]
func (h *CourseHandler) DeleteSection(c *gin.Context) {
	sectionID, err := strconv.ParseInt(c.Param("sectionId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid section ID"))
		return
	}

	userID := c.GetInt64("user_id")
	role := c.GetString("user_role")

	err = h.courseService.DeleteSection(c.Request.Context(), sectionID, userID, role)
	if err != nil {
		if err.Error() == "section not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Section not found"))
			return
		}
		if err.Error() == "unauthorized to delete this section" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to delete section", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to delete section"))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Section deleted successfully"))
}

// ===== CONTENT HANDLERS =====

// CreateContent creates new content in a section
// @Summary Create content
// @Description Create new content in a section (Owner/Admin only)
// @Tags content
// @Accept json
// @Produce json
// @Param sectionId path int true "Section ID"
// @Param content body dto.CreateContentRequest true "Content data"
// @Security BearerAuth
// @Success 201 {object} dto.ContentResponse
// @Failure 400 {object} dto.ErrorResponse
// @Failure 403 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /sections/{sectionId}/content [post]
func (h *CourseHandler) CreateContent(c *gin.Context) {
	sectionID, err := strconv.ParseInt(c.Param("sectionId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid section ID"))
		return
	}

	var req dto.CreateContentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}

	userID := c.GetInt64("user_id")
	role := c.GetString("user_role")

	content, err := h.courseService.CreateContent(c.Request.Context(), sectionID, &req, userID, role)
	if err != nil {
		if err.Error() == "section not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Section not found"))
			return
		}
		if err.Error() == "unauthorized to create content in this section" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to create content", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to create content"))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(content))
}

// GetContent retrieves content by ID
// @Summary Get content
// @Description Get content details by ID
// @Tags content
// @Accept json
// @Produce json
// @Param contentId path int true "Content ID"
// @Security BearerAuth
// @Success 200 {object} dto.ContentResponse
// @Failure 404 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /content/{contentId} [get]
func (h *CourseHandler) GetContent(c *gin.Context) {
	contentID, err := strconv.ParseInt(c.Param("contentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid content ID"))
		return
	}

	userID := c.GetInt64("user_id")
	role := c.GetString("user_role")

	content, err := h.courseService.GetContent(c.Request.Context(), contentID, userID, role)
	if err != nil {
		if err.Error() == "content not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Content not found"))
			return
		}
		if err.Error() == "unauthorized to view this content" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to get content", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve content"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(content))
}

// ListContent lists all content in a section
// @Summary List content
// @Description List all content in a section
// @Tags content
// @Accept json
// @Produce json
// @Param sectionId path int true "Section ID"
// @Security BearerAuth
// @Success 200 {array} dto.ContentResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /sections/{sectionId}/content [get]
func (h *CourseHandler) ListContent(c *gin.Context) {
	sectionID, err := strconv.ParseInt(c.Param("sectionId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid section ID"))
		return
	}

	userID := c.GetInt64("user_id")
	role := c.GetString("user_role")

	contents, err := h.courseService.ListContent(c.Request.Context(), sectionID, userID, role)
	if err != nil {
		if err.Error() == "section not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Section not found"))
			return
		}
		logger.Error("Failed to list content", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve content"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(contents))
}

// UpdateContent updates content
// @Summary Update content
// @Description Update content details (Owner/Admin only)
// @Tags content
// @Accept json
// @Produce json
// @Param contentId path int true "Content ID"
// @Param content body dto.UpdateContentRequest true "Content data"
// @Security BearerAuth
// @Success 200 {object} dto.MessageResponse
// @Failure 400 {object} dto.ErrorResponse
// @Failure 403 {object} dto.ErrorResponse
// @Failure 404 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /content/{contentId} [put]
func (h *CourseHandler) UpdateContent(c *gin.Context) {
	contentID, err := strconv.ParseInt(c.Param("contentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid content ID"))
		return
	}

	var req dto.UpdateContentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}

	userID := c.GetInt64("user_id")
	role := c.GetString("user_role")

	err = h.courseService.UpdateContent(c.Request.Context(), contentID, &req, userID, role)
	if err != nil {
		if err.Error() == "content not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Content not found"))
			return
		}
		if err.Error() == "unauthorized to update this content" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to update content", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to update content"))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Content updated successfully"))
}

// DeleteContent deletes content
// @Summary Delete content
// @Description Delete content (Owner/Admin only)
// @Tags content
// @Accept json
// @Produce json
// @Param contentId path int true "Content ID"
// @Security BearerAuth
// @Success 200 {object} dto.MessageResponse
// @Failure 403 {object} dto.ErrorResponse
// @Failure 404 {object} dto.ErrorResponse
// @Failure 500 {object} dto.ErrorResponse
// @Router /content/{contentId} [delete]
func (h *CourseHandler) DeleteContent(c *gin.Context) {
	contentID, err := strconv.ParseInt(c.Param("contentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid content ID"))
		return
	}

	userID := c.GetInt64("user_id")
	role := c.GetString("user_role")

	err = h.courseService.DeleteContent(c.Request.Context(), contentID, userID, role)
	if err != nil {
		if err.Error() == "content not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Content not found"))
			return
		}
		if err.Error() == "unauthorized to delete this content" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to delete content", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to delete content"))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Content deleted successfully"))
}