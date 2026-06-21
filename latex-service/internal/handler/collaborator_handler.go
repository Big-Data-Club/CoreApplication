package handler

import (
	"net/http"
	"strconv"

	"latex-service/internal/dto"
	"latex-service/internal/service"

	"github.com/gin-gonic/gin"
)

// CollaboratorHandler handles collaborator management endpoints
type CollaboratorHandler struct {
	collabService *service.CollaboratorService
}

// NewCollaboratorHandler creates a new CollaboratorHandler
func NewCollaboratorHandler(collabService *service.CollaboratorService) *CollaboratorHandler {
	return &CollaboratorHandler{collabService: collabService}
}

// Add handles POST /projects/:id/collaborators
func (h *CollaboratorHandler) Add(c *gin.Context) {
	projectID, ok := parseProjectID(c)
	if !ok {
		return
	}
	userID, ok := extractUserID(c)
	if !ok {
		return
	}

	var req dto.AddCollaboratorRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", err.Error()))
		return
	}

	result, err := h.collabService.AddCollaborator(c.Request.Context(), projectID, userID, &req)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("add_collaborator_failed", err.Error()))
		return
	}
	c.JSON(http.StatusCreated, dto.NewDataResponse(result))
}

// List handles GET /projects/:id/collaborators
func (h *CollaboratorHandler) List(c *gin.Context) {
	projectID, ok := parseProjectID(c)
	if !ok {
		return
	}
	userID, ok := extractUserID(c)
	if !ok {
		return
	}

	result, err := h.collabService.ListCollaborators(c.Request.Context(), projectID, userID)
	if err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("access_denied", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// UpdateRole handles PUT /projects/:id/collaborators/:userId
func (h *CollaboratorHandler) UpdateRole(c *gin.Context) {
	projectID, ok := parseProjectID(c)
	if !ok {
		return
	}
	userID, ok := extractUserID(c)
	if !ok {
		return
	}

	targetUserIDStr := c.Param("userId")
	targetUserID, err := strconv.ParseInt(targetUserIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid user ID"))
		return
	}

	var req dto.UpdateCollaboratorRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", err.Error()))
		return
	}

	result, err := h.collabService.UpdateRole(c.Request.Context(), projectID, userID, targetUserID, req.Role)
	if err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("update_role_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// Remove handles DELETE /projects/:id/collaborators/:userId
func (h *CollaboratorHandler) Remove(c *gin.Context) {
	projectID, ok := parseProjectID(c)
	if !ok {
		return
	}
	userID, ok := extractUserID(c)
	if !ok {
		return
	}

	targetUserIDStr := c.Param("userId")
	targetUserID, err := strconv.ParseInt(targetUserIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid user ID"))
		return
	}

	if err := h.collabService.RemoveCollaborator(c.Request.Context(), projectID, userID, targetUserID); err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("remove_collaborator_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Collaborator removed successfully"))
}

// ── helpers shared across handlers ──────────────────────────────────────────

func parseProjectID(c *gin.Context) (int64, bool) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid project ID"))
		return 0, false
	}
	return id, true
}

func extractUserID(c *gin.Context) (int64, bool) {
	v, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return 0, false
	}
	return v.(int64), true
}

func extractUserEmail(c *gin.Context) string {
	v, _ := c.Get("user_email")
	if v == nil {
		return ""
	}
	return v.(string)
}
