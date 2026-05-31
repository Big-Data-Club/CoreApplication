package handler

import (
	"net/http"
	"strconv"

	"lab-service/internal/dto"
	"lab-service/internal/service"

	"github.com/gin-gonic/gin"
)

type LabHandler struct {
	labService *service.LabService
}

func NewLabHandler(labService *service.LabService) *LabHandler {
	return &LabHandler{labService: labService}
}

func (h *LabHandler) CreateLab(c *gin.Context) {
	var req dto.CreateLabRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	userID := c.GetInt64("user_id")
	lab, status, err := h.labService.CreateLab(c.Request.Context(), &req, userID)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewSuccessResponse("Lab created", lab))
}

func (h *LabHandler) GetLab(c *gin.Context) {
	labID, err := strconv.ParseInt(c.Param("labId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid lab ID"))
		return
	}
	lab, status, err := h.labService.GetLab(c.Request.Context(), labID)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewDataResponse(lab))
}

func (h *LabHandler) ListPublishedLabs(c *gin.Context) {
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))
	labType := c.Query("lab_type")
	category := c.Query("category")
	level := c.Query("level")
	search := c.Query("search")

	resp, status, err := h.labService.ListPublishedLabs(c.Request.Context(), labType, category, level, search, page, pageSize)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, resp)
}

func (h *LabHandler) ListMyLabs(c *gin.Context) {
	userID := c.GetInt64("user_id")
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))
	status := c.Query("status")

	resp, st, err := h.labService.ListMyLabs(c.Request.Context(), userID, status, page, pageSize)
	if err != nil {
		c.JSON(st, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(st, resp)
}

func (h *LabHandler) UpdateLab(c *gin.Context) {
	labID, err := strconv.ParseInt(c.Param("labId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid lab ID"))
		return
	}
	var req dto.UpdateLabRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	userID := c.GetInt64("user_id")
	userRole := c.GetString("user_role")
	status, err := h.labService.UpdateLab(c.Request.Context(), labID, &req, userID, userRole)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewMessageResponse("Lab updated"))
}

func (h *LabHandler) DeleteLab(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	userID := c.GetInt64("user_id")
	userRole := c.GetString("user_role")
	status, err := h.labService.DeleteLab(c.Request.Context(), labID, userID, userRole)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewMessageResponse("Lab deleted"))
}

func (h *LabHandler) PublishLab(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	userID := c.GetInt64("user_id")
	userRole := c.GetString("user_role")
	status, err := h.labService.PublishLab(c.Request.Context(), labID, userID, userRole)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewMessageResponse("Lab published"))
}

// ── Sections ────────────────────────────────────────────────────

func (h *LabHandler) CreateSection(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	var req dto.CreateSectionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	userID := c.GetInt64("user_id")
	userRole := c.GetString("user_role")
	sec, status, err := h.labService.CreateSection(c.Request.Context(), labID, &req, userID, userRole)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewSuccessResponse("Section created", sec))
}

func (h *LabHandler) ListSections(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	sections, status, err := h.labService.ListSections(c.Request.Context(), labID)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewDataResponse(sections))
}

func (h *LabHandler) UpdateSection(c *gin.Context) {
	sectionID, _ := strconv.ParseInt(c.Param("sectionId"), 10, 64)
	var req dto.UpdateSectionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	status, err := h.labService.UpdateSection(c.Request.Context(), sectionID, &req)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewMessageResponse("Section updated"))
}

func (h *LabHandler) DeleteSection(c *gin.Context) {
	sectionID, _ := strconv.ParseInt(c.Param("sectionId"), 10, 64)
	status, err := h.labService.DeleteSection(c.Request.Context(), sectionID)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewMessageResponse("Section deleted"))
}

// ── Content ─────────────────────────────────────────────────────

func (h *LabHandler) CreateContent(c *gin.Context) {
	sectionID, _ := strconv.ParseInt(c.Param("sectionId"), 10, 64)
	var req dto.CreateContentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	userID := c.GetInt64("user_id")
	content, status, err := h.labService.CreateContent(c.Request.Context(), sectionID, &req, userID)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewSuccessResponse("Content created", content))
}

func (h *LabHandler) ListContent(c *gin.Context) {
	sectionID, _ := strconv.ParseInt(c.Param("sectionId"), 10, 64)
	contents, status, err := h.labService.ListContent(c.Request.Context(), sectionID)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewDataResponse(contents))
}
