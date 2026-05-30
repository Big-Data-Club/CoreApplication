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

type OrganizationHandler struct {
	orgService *service.OrganizationService
}

func NewOrganizationHandler(orgService *service.OrganizationService) *OrganizationHandler {
	return &OrganizationHandler{orgService: orgService}
}

// ListOrganizations lists all organizations (Super Admin only)
// @Summary List organizations
// @Tags organizations
// @Produce json
// @Security BearerAuth
// @Success 200 {object} dto.ListResponse
// @Router /admin/organizations [get]
func (h *OrganizationHandler) ListOrganizations(c *gin.Context) {
	var pagination dto.PaginationRequest
	if err := c.ShouldBindQuery(&pagination); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	search := c.Query("search")
	limit, offset := pagination.GetPagination()

	orgs, total, err := h.orgService.ListOrganizations(c.Request.Context(), limit, offset, search)
	if err != nil {
		logger.Error("Failed to list organizations", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve organizations"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(dto.NewListResponse(orgs, pagination.Page, limit, total)))
}

// CreateOrganization creates a new organization (Super Admin only)
// @Summary Create organization
// @Tags organizations
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param org body dto.CreateOrgRequest true "Organization data"
// @Success 201 {object} dto.OrgResponse
// @Router /admin/organizations [post]
func (h *OrganizationHandler) CreateOrganization(c *gin.Context) {
	var req dto.CreateOrgRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}

	userID := c.GetInt64("user_id")
	role := getRoleFromContext(c)

	org, err := h.orgService.CreateOrganization(c.Request.Context(), &req, userID, role)
	if err != nil {
		if err.Error() == "only Super Admin can create organizations" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		if err.Error() != "" && len(err.Error()) > 20 && err.Error()[:20] == "organization with sl" {
			c.JSON(http.StatusConflict, dto.NewErrorResponse("conflict", err.Error()))
			return
		}
		logger.Error("Failed to create organization", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to create organization"))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(org))
}

// GetOrganization retrieves an organization by ID
// @Summary Get organization
// @Tags organizations
// @Produce json
// @Security BearerAuth
// @Param id path int true "Organization ID"
// @Success 200 {object} dto.OrgResponse
// @Router /admin/organizations/{id} [get]
func (h *OrganizationHandler) GetOrganization(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid organization ID"))
		return
	}

	org, err := h.orgService.GetOrganization(c.Request.Context(), id)
	if err != nil {
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Organization not found"))
			return
		}
		logger.Error("Failed to get organization", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve organization"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(org))
}

// UpdateOrganization updates an organization
// @Summary Update organization
// @Tags organizations
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param id path int true "Organization ID"
// @Param org body dto.UpdateOrgRequest true "Update data"
// @Success 200 {object} dto.OrgResponse
// @Router /admin/organizations/{id} [put]
func (h *OrganizationHandler) UpdateOrganization(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid organization ID"))
		return
	}

	var req dto.UpdateOrgRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}

	userID := c.GetInt64("user_id")
	role := getRoleFromContext(c)

	org, err := h.orgService.UpdateOrganization(c.Request.Context(), id, &req, userID, role)
	if err != nil {
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Organization not found"))
			return
		}
		if err.Error() == "unauthorized to update this organization" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to update organization", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to update organization"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(org))
}

// DeactivateOrganization deactivates an organization (Super Admin only)
// @Summary Deactivate organization
// @Tags organizations
// @Produce json
// @Security BearerAuth
// @Param id path int true "Organization ID"
// @Success 200 {object} dto.MessageResponse
// @Router /admin/organizations/{id} [delete]
func (h *OrganizationHandler) DeactivateOrganization(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid organization ID"))
		return
	}

	role := getRoleFromContext(c)

	if err := h.orgService.DeactivateOrganization(c.Request.Context(), id, role); err != nil {
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Organization not found"))
			return
		}
		if err.Error() == "only Super Admin can deactivate organizations" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to deactivate organization", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to deactivate organization"))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Organization deactivated successfully"))
}

// GetOrgStats returns statistics for an organization
// @Summary Get organization stats
// @Tags organizations
// @Produce json
// @Security BearerAuth
// @Param id path int true "Organization ID"
// @Success 200 {object} dto.OrgStatsResponse
// @Router /admin/organizations/{id}/stats [get]
func (h *OrganizationHandler) GetOrgStats(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid organization ID"))
		return
	}

	stats, err := h.orgService.GetOrgStats(c.Request.Context(), id)
	if err != nil {
		logger.Error("Failed to get org stats", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve organization statistics"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(stats))
}

// ListMembers lists members of an organization
// @Summary List org members
// @Tags organizations
// @Produce json
// @Security BearerAuth
// @Param id path int true "Organization ID"
// @Success 200 {object} dto.ListResponse
// @Router /admin/organizations/{id}/members [get]
func (h *OrganizationHandler) ListMembers(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid organization ID"))
		return
	}

	var pagination dto.PaginationRequest
	if err := c.ShouldBindQuery(&pagination); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	limit, offset := pagination.GetPagination()

	members, total, err := h.orgService.ListMembers(c.Request.Context(), id, limit, offset)
	if err != nil {
		logger.Error("Failed to list org members", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve members"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(dto.NewListResponse(members, pagination.Page, limit, total)))
}

// AddMember adds a user to an organization
// @Summary Add org member
// @Tags organizations
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param id path int true "Organization ID"
// @Param member body dto.AddMemberRequest true "Member data"
// @Success 200 {object} dto.MessageResponse
// @Router /admin/organizations/{id}/members [post]
func (h *OrganizationHandler) AddMember(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid organization ID"))
		return
	}

	var req dto.AddMemberRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}

	userID := c.GetInt64("user_id")
	role := getRoleFromContext(c)

	if err := h.orgService.AddMember(c.Request.Context(), id, &req, userID, role); err != nil {
		if err.Error() == "unauthorized to manage members of this organization" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		if err.Error() == "user not found" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", err.Error()))
			return
		}
		logger.Error("Failed to add org member", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to add member"))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Member added successfully"))
}

// UpdateMemberRole updates a member's role in an organization
// @Summary Update member role
// @Tags organizations
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param id path int true "Organization ID"
// @Param userId path int true "User ID"
// @Param role body dto.UpdateMemberRoleRequest true "New role"
// @Success 200 {object} dto.MessageResponse
// @Router /admin/organizations/{id}/members/{userId}/role [put]
func (h *OrganizationHandler) UpdateMemberRole(c *gin.Context) {
	orgID, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid organization ID"))
		return
	}

	targetUserID, err := strconv.ParseInt(c.Param("userId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid user ID"))
		return
	}

	var req dto.UpdateMemberRoleRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}

	actorID := c.GetInt64("user_id")
	role := getRoleFromContext(c)

	if err := h.orgService.UpdateMemberRole(c.Request.Context(), orgID, targetUserID, &req, actorID, role); err != nil {
		if err.Error() == "unauthorized to update roles in this organization" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		if err.Error() == "user is not a member of this organization" {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", err.Error()))
			return
		}
		logger.Error("Failed to update member role", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to update member role"))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Member role updated successfully"))
}

// RemoveMember removes a user from an organization
// @Summary Remove org member
// @Tags organizations
// @Produce json
// @Security BearerAuth
// @Param id path int true "Organization ID"
// @Param userId path int true "User ID"
// @Success 200 {object} dto.MessageResponse
// @Router /admin/organizations/{id}/members/{userId} [delete]
func (h *OrganizationHandler) RemoveMember(c *gin.Context) {
	orgID, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid organization ID"))
		return
	}

	targetUserID, err := strconv.ParseInt(c.Param("userId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid user ID"))
		return
	}

	actorID := c.GetInt64("user_id")
	role := getRoleFromContext(c)

	if err := h.orgService.RemoveMember(c.Request.Context(), orgID, targetUserID, actorID, role); err != nil {
		if err.Error() == "unauthorized to remove this member" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Member not found"))
			return
		}
		logger.Error("Failed to remove org member", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to remove member"))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Member removed successfully"))
}

// GetMyOrganizations lists organizations the authenticated user belongs to
// @Summary Get my organizations
// @Tags organizations
// @Produce json
// @Security BearerAuth
// @Success 200 {array} dto.OrgResponse
// @Router /my/orgs [get]
func (h *OrganizationHandler) GetMyOrganizations(c *gin.Context) {
	userID := c.GetInt64("user_id")

	orgs, err := h.orgService.GetUserOrgs(c.Request.Context(), userID)
	if err != nil {
		logger.Error("Failed to get user organizations", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve organizations"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(orgs))
}

// BulkAddMembers adds multiple members to an organization by email (Admin only)
// @Summary Bulk add org members
// @Tags organizations
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param id path int true "Organization ID"
// @Param request body dto.BulkAddMembersRequest true "Bulk add request data"
// @Success 200 {object} dto.BulkAddMembersResponse
// @Router /admin/organizations/{id}/members/bulk [post]
func (h *OrganizationHandler) BulkAddMembers(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid organization ID"))
		return
	}

	var req dto.BulkAddMembersRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}

	userID := c.GetInt64("user_id")
	role := getRoleFromContext(c)

	result, err := h.orgService.BulkAddMembers(c.Request.Context(), id, &req, userID, role)
	if err != nil {
		if err.Error() == "unauthorized to manage members of this organization" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", err.Error()))
			return
		}
		logger.Error("Failed to bulk add org members", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to bulk add members"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}
