package handler

import (
	"chat-service/internal/dto"
	"chat-service/internal/repository"
	"chat-service/pkg/logger"

	"github.com/gin-gonic/gin"
)

// SyncHandler handles user sync requests from auth-and-management-service.
// Protected by X-Sync-Secret header - never exposed to public JWT users.
type SyncHandler struct {
	userRepo *repository.UserRepository
	chatRepo *repository.ChatRepository
}

func NewSyncHandler(userRepo *repository.UserRepository, chatRepo *repository.ChatRepository) *SyncHandler {
	return &SyncHandler{userRepo: userRepo, chatRepo: chatRepo}
}

// SyncUser handles POST /api/v1/sync/user
// Called by auth-service when a single user is created or updated.
func (h *SyncHandler) SyncUser(c *gin.Context) {
	var req dto.SyncUserRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(dto.ErrBadRequest(err.Error()))
		return
	}

	u := repository.User{
		ID:             req.ID,
		Email:          req.Email,
		FullName:       req.FullName,
		ProfilePicture: req.ProfilePicture,
	}

	if err := h.userRepo.Upsert(c.Request.Context(), u); err != nil {
		logger.Errorf("sync user %d: %v", req.ID, err)
		c.JSON(dto.ErrInternal("Failed to sync user"))
		return
	}

	// Try to seed default channel if this is the first synced user
	if seeded, err := h.chatRepo.SeedDefaultChannel(c.Request.Context()); err == nil && seeded {
		logger.Infof("Successfully seeded default channel using user %d", req.ID)
	} else if err != nil {
		logger.Warnf("Failed to seed default channel during user sync %d: %v", req.ID, err)
	}

	c.JSON(dto.OK(gin.H{"synced": true}))
}

// BulkSyncUsers handles POST /api/v1/sync/users/bulk
// Called by auth-service on startup or bulk import.
func (h *SyncHandler) BulkSyncUsers(c *gin.Context) {
	var req dto.BulkSyncUsersRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(dto.ErrBadRequest(err.Error()))
		return
	}

	users := make([]repository.User, len(req.Users))
	for i, u := range req.Users {
		users[i] = repository.User{
			ID:             u.ID,
			Email:          u.Email,
			FullName:       u.FullName,
			ProfilePicture: u.ProfilePicture,
		}
	}

	if err := h.userRepo.BulkUpsert(c.Request.Context(), users); err != nil {
		logger.Errorf("bulk sync: %v", err)
		c.JSON(dto.ErrInternal("Failed to bulk sync users"))
		return
	}

	// Try to seed default channel
	if seeded, err := h.chatRepo.SeedDefaultChannel(c.Request.Context()); err == nil && seeded {
		logger.Info("Successfully seeded default channel during bulk sync")
	} else if err != nil {
		logger.Warnf("Failed to seed default channel during bulk sync: %v", err)
	}

	logger.Infof("Bulk synced %d users", len(users))
	c.JSON(dto.OK(gin.H{"synced": len(users)}))
}

// DeleteUser handles DELETE /api/v1/sync/user/:userId
// auth-service calls this when a user is deleted.
// We do NOT delete chat messages (historical record); just respond OK.
// A full GDPR hard-delete can be added via a background job later.
func (h *SyncHandler) DeleteUser(c *gin.Context) {
	c.JSON(dto.OK(gin.H{"success": true}))
}
