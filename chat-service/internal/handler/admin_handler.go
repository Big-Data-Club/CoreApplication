package handler

import (
	"chat-service/internal/dto"
	"chat-service/internal/repository"
	"chat-service/pkg/logger"

	"github.com/gin-gonic/gin"
)

// AdminHandler handles admin-only channel and role management endpoints.
type AdminHandler struct {
	chatRepo *repository.ChatRepository
	userRepo *repository.UserRepository
}

func NewAdminHandler(chatRepo *repository.ChatRepository, userRepo *repository.UserRepository) *AdminHandler {
	return &AdminHandler{chatRepo: chatRepo, userRepo: userRepo}
}

// ─── ListAllChannels GET /api/v1/admin/channels ──────────────────────────────

func (h *AdminHandler) ListAllChannels(c *gin.Context) {
	channels, err := h.chatRepo.ListAllChannels(c.Request.Context())
	if err != nil {
		logger.Errorf("admin list channels: %v", err)
		c.JSON(dto.ErrInternal("Failed to list channels"))
		return
	}

	resp := make([]dto.ChannelResponse, len(channels))
	for i, ch := range channels {
		resp[i] = channelToDTO(ch)
	}
	c.JSON(dto.OK(resp))
}

// ─── CreateChannel POST /api/v1/admin/channels ───────────────────────────────

func (h *AdminHandler) CreateChannel(c *gin.Context) {
	var req dto.CreateChannelRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(dto.ErrBadRequest(err.Error()))
		return
	}

	userID := mustUserID(c)

	// Ensure admin user exists in chat DB
	if err := h.userRepo.EnsureGuestUser(c.Request.Context(), userID, c.GetString("user_email")); err != nil {
		logger.Warnf("ensure admin user %d: %v", userID, err)
	}

	ch, err := h.chatRepo.CreateChannel(
		c.Request.Context(),
		req.Slug, req.Name, req.Description, req.IsPrivate, userID,
	)
	if err != nil {
		logger.Errorf("create channel: %v", err)
		c.JSON(dto.ErrInternal("Failed to create channel (slug may already exist)"))
		return
	}

	c.JSON(dto.Created(channelToDTO(*ch)))
}

// ─── UpdateChannel PUT /api/v1/admin/channels/:id ────────────────────────────

func (h *AdminHandler) UpdateChannel(c *gin.Context) {
	id, ok := parseID(c, "id")
	if !ok {
		return
	}

	var req dto.UpdateChannelRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(dto.ErrBadRequest(err.Error()))
		return
	}

	ch, err := h.chatRepo.UpdateChannel(c.Request.Context(), id, req.Name, req.Description, req.IsPrivate)
	if err != nil {
		c.JSON(dto.ErrInternal("Failed to update channel"))
		return
	}
	if ch == nil {
		c.JSON(dto.ErrNotFound("Channel not found"))
		return
	}

	c.JSON(dto.OK(channelToDTO(*ch)))
}

// ─── DeleteChannel DELETE /api/v1/admin/channels/:id ─────────────────────────

func (h *AdminHandler) DeleteChannel(c *gin.Context) {
	id, ok := parseID(c, "id")
	if !ok {
		return
	}

	if err := h.chatRepo.DeleteChannel(c.Request.Context(), id); err != nil {
		c.JSON(dto.ErrInternal("Failed to delete channel"))
		return
	}

	c.JSON(dto.OK(gin.H{"deleted": true}))
}

// ─── GetChannelRoles GET /api/v1/admin/channels/:id/roles ────────────────────

func (h *AdminHandler) GetChannelRoles(c *gin.Context) {
	id, ok := parseID(c, "id")
	if !ok {
		return
	}

	roles, err := h.chatRepo.GetChannelRoles(c.Request.Context(), id)
	if err != nil {
		c.JSON(dto.ErrInternal("Failed to get roles"))
		return
	}

	resp := make([]dto.ChannelRoleEntry, len(roles))
	for i, r := range roles {
		resp[i] = dto.ChannelRoleEntry{
			RoleName: r.RoleName,
			CanRead:  r.CanRead,
			CanWrite: r.CanWrite,
		}
	}
	c.JSON(dto.OK(resp))
}

// ─── SetChannelRoles PUT /api/v1/admin/channels/:id/roles ────────────────────

func (h *AdminHandler) SetChannelRoles(c *gin.Context) {
	id, ok := parseID(c, "id")
	if !ok {
		return
	}

	var req dto.SetChannelRolesRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(dto.ErrBadRequest(err.Error()))
		return
	}

	roles := make([]repository.ChannelRole, len(req.Roles))
	for i, r := range req.Roles {
		roles[i] = repository.ChannelRole{
			ChannelID: id,
			RoleName:  r.RoleName,
			CanRead:   r.CanRead,
			CanWrite:  r.CanWrite,
		}
	}

	if err := h.chatRepo.SetChannelRoles(c.Request.Context(), id, roles); err != nil {
		c.JSON(dto.ErrInternal("Failed to set roles"))
		return
	}

	c.JSON(dto.OK(gin.H{"updated": true}))
}

// ─── GetChannelUsers GET /api/v1/admin/channels/:id/users ────────────────────

func (h *AdminHandler) GetChannelUsers(c *gin.Context) {
	id, ok := parseID(c, "id")
	if !ok {
		return
	}

	userIDs, err := h.chatRepo.GetChannelUsers(c.Request.Context(), id)
	if err != nil {
		c.JSON(dto.ErrInternal("Failed to get whitelist"))
		return
	}

	c.JSON(dto.OK(gin.H{"user_ids": userIDs}))
}

// ─── SetChannelUsers PUT /api/v1/admin/channels/:id/users ────────────────────

func (h *AdminHandler) SetChannelUsers(c *gin.Context) {
	id, ok := parseID(c, "id")
	if !ok {
		return
	}

	var req dto.SetChannelUsersRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(dto.ErrBadRequest(err.Error()))
		return
	}

	if err := h.chatRepo.SetChannelUsers(c.Request.Context(), id, req.UserIDs); err != nil {
		c.JSON(dto.ErrInternal("Failed to set whitelist"))
		return
	}

	c.JSON(dto.OK(gin.H{"updated": true}))
}
