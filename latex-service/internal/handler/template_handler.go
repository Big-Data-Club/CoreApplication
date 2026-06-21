package handler

import (
	"net/http"

	"latex-service/internal/dto"
	"latex-service/internal/service"

	"github.com/gin-gonic/gin"
)

type TemplateHandler struct {
	templateService *service.TemplateService
}

func NewTemplateHandler(templateService *service.TemplateService) *TemplateHandler {
	return &TemplateHandler{templateService: templateService}
}

// ListTemplates handles retrieving all available templates
func (h *TemplateHandler) ListTemplates(c *gin.Context) {
	templates := h.templateService.GetTemplates()
	c.JSON(http.StatusOK, dto.NewDataResponse(templates))
}

// GetTemplate handles retrieving a specific template's details
func (h *TemplateHandler) GetTemplate(c *gin.Context) {
	id := c.Param("id")
	template, err := h.templateService.GetTemplate(id)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(template))
}

// CreateFromTemplate handles creating a project from a template
func (h *TemplateHandler) CreateFromTemplate(c *gin.Context) {
	templateID := c.Param("id")

	var req struct {
		Title string `json:"title" binding:"required,min=1,max=255"`
	}
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

	project, err := h.templateService.CreateProjectFromTemplate(c.Request.Context(), userID, templateID, req.Title)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("creation_failed", err.Error()))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(project))
}

// ListPackages handles package listing and searching
func (h *TemplateHandler) ListPackages(c *gin.Context) {
	query := c.Query("q")
	packages := h.templateService.SearchPackages(query)
	c.JSON(http.StatusOK, dto.NewDataResponse(packages))
}
