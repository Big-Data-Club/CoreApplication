package handler

import (
	"net/http"
	"strconv"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
)

// PermissionHandler exposes admin endpoints for permission management.
type PermissionHandler struct {
	permService *service.PermissionService
}

func NewPermissionHandler(permService *service.PermissionService) *PermissionHandler {
	return &PermissionHandler{permService: permService}
}

// ListPermissions returns the master list of all permissions.
// GET /api/v1/admin/permissions
func (h *PermissionHandler) ListPermissions(c *gin.Context) {
	perms, err := h.permService.ListAll(c.Request.Context())
	if err != nil {
		logger.Error("ListPermissions failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(perms))
}

// GetRolePermissions returns the permissions assigned to a specific role.
// GET /api/v1/admin/roles/:id/permissions
func (h *PermissionHandler) GetRolePermissions(c *gin.Context) {
	roleID, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid role ID"))
		return
	}

	resp, err := h.permService.GetRolePermissions(c.Request.Context(), roleID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(resp))
}

// AssignPermissions replaces the permissions for a role.
// PUT /api/v1/admin/roles/:id/permissions
func (h *PermissionHandler) AssignPermissions(c *gin.Context) {
	roleID, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid role ID"))
		return
	}

	var body dto.AssignPermissionsRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	if err := h.permService.AssignPermissions(c.Request.Context(), roleID, body.PermissionIDs); err != nil {
		logger.Error("AssignPermissions failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("db_error", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Permissions updated"))
}
