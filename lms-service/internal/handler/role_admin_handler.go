package handler

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"

	"example/hello/internal/dto"
	"example/hello/internal/service"
)

type RoleAdminHandler struct {
	roleService *service.RoleAdminService
}

func NewRoleAdminHandler(roleService *service.RoleAdminService) *RoleAdminHandler {
	return &RoleAdminHandler{roleService: roleService}
}

func (h *RoleAdminHandler) ListRoles(c *gin.Context) {
	roles, err := h.roleService.ListRoles(c.Request.Context())
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, roles)
}

func (h *RoleAdminHandler) CreateRole(c *gin.Context) {
	var req dto.RoleDefinitionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	role, err := h.roleService.CreateRole(c.Request.Context(), &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("creation_failed", err.Error()))
		return
	}

	c.JSON(http.StatusCreated, role)
}

func (h *RoleAdminHandler) UpdateRole(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid role ID"))
		return
	}

	var req dto.RoleDefinitionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	if err := h.roleService.UpdateRole(c.Request.Context(), id, &req); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("update_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Role updated successfully"})
}

func (h *RoleAdminHandler) DeleteRole(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid role ID"))
		return
	}

	if err := h.roleService.DeleteRole(c.Request.Context(), id); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("delete_failed", err.Error()))
		return
	}

	c.JSON(http.StatusNoContent, nil)
}

func (h *RoleAdminHandler) GetUserRoles(c *gin.Context) {
	idStr := c.Param("userId")
	userID, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid user ID"))
		return
	}

	roles, err := h.roleService.GetUserRoles(c.Request.Context(), userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("fetch_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, roles)
}

func (h *RoleAdminHandler) AssignRoleToUser(c *gin.Context) {
	idStr := c.Param("userId")
	userID, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid user ID"))
		return
	}

	var req dto.AssignRoleRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	roleName := strings.ToUpper(req.Role)
	if err := h.roleService.AssignRoleToUser(c.Request.Context(), userID, roleName); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("assign_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Role assigned successfully"})
}

func (h *RoleAdminHandler) RemoveRoleFromUser(c *gin.Context) {
	idStr := c.Param("userId")
	userID, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid user ID"))
		return
	}

	roleName := strings.ToUpper(c.Param("role"))
	if err := h.roleService.RemoveRoleFromUser(c.Request.Context(), userID, roleName); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("remove_failed", err.Error()))
		return
	}

	c.JSON(http.StatusNoContent, nil)
}
