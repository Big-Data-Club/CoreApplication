package handler

import (
	"net/http"
	"strconv"

	"latex-service/internal/dto"
	"latex-service/internal/service"

	"github.com/gin-gonic/gin"
)

type ProjectHandler struct {
	projectService *service.ProjectService
}

func NewProjectHandler(projectService *service.ProjectService) *ProjectHandler {
	return &ProjectHandler{projectService: projectService}
}

// Create handles project creation
func (h *ProjectHandler) Create(c *gin.Context) {
	var req dto.CreateProjectRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", err.Error()))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	res, err := h.projectService.CreateProject(c.Request.Context(), &req, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(res))
}

// Get handles project retrieval
func (h *ProjectHandler) Get(c *gin.Context) {
	projectIDStr := c.Param("id")
	projectID, err := strconv.ParseInt(projectIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid project ID"))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	res, err := h.projectService.GetProject(c.Request.Context(), projectID, userID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(res))
}

// List handles listing user's projects
func (h *ProjectHandler) List(c *gin.Context) {
	pageStr := c.DefaultQuery("page", "1")
	limitStr := c.DefaultQuery("limit", "10")

	page, err := strconv.Atoi(pageStr)
	if err != nil || page < 1 {
		page = 1
	}

	limit, err := strconv.Atoi(limitStr)
	if err != nil || limit < 1 {
		limit = 10
	}
	if limit > 100 {
		limit = 100
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	offset := (page - 1) * limit
	res, total, err := h.projectService.ListProjects(c.Request.Context(), userID, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(dto.NewListResponse(res, page, limit, total)))
}

// Update handles updating project metadata
func (h *ProjectHandler) Update(c *gin.Context) {
	projectIDStr := c.Param("id")
	projectID, err := strconv.ParseInt(projectIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid project ID"))
		return
	}

	var req dto.UpdateProjectRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", err.Error()))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	res, err := h.projectService.UpdateProject(c.Request.Context(), projectID, userID, &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(res))
}

// Delete handles deleting a project
func (h *ProjectHandler) Delete(c *gin.Context) {
	projectIDStr := c.Param("id")
	projectID, err := strconv.ParseInt(projectIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid project ID"))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	err = h.projectService.DeleteProject(c.Request.Context(), projectID, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Project deleted successfully"))
}
