package handler

import (
	"net/http"

	"lab-service/internal/dto"
	"lab-service/internal/repository"

	"github.com/gin-gonic/gin"
)

type SyncHandler struct {
	userRepo *repository.UserRepository
}

func NewSyncHandler(userRepo *repository.UserRepository) *SyncHandler {
	return &SyncHandler{userRepo: userRepo}
}

func (h *SyncHandler) SyncUser(c *gin.Context) {
	var req repository.UserSyncRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	if err := h.userRepo.SyncUser(c.Request.Context(), &req); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("User synced"))
}

func (h *SyncHandler) BulkSyncUsers(c *gin.Context) {
	var req struct {
		Users []repository.UserSyncRequest `json:"users" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	if err := h.userRepo.BulkSyncUsers(c.Request.Context(), req.Users); err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewSuccessResponse("Users synced", map[string]int{"count": len(req.Users)}))
}
