package handler

import (
	"net/http"
	"strconv"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
)

type UserSyncHandler struct {
	syncService *service.UserSyncService
	syncSecret  string
}

func NewUserSyncHandler(syncService *service.UserSyncService, syncSecret string) *UserSyncHandler {
	return &UserSyncHandler{
		syncService: syncService,
		syncSecret:  syncSecret,
	}
}

// SyncSecret middleware validates the sync secret
func (h *UserSyncHandler) SyncSecret() gin.HandlerFunc {
	return func(c *gin.Context) {
		secret := c.GetHeader("X-Sync-Secret")
		if secret == "" || secret != h.syncSecret {
			c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Invalid sync secret"))
			c.Abort()
			return
		}
		c.Next()
	}
}

// SyncUser godoc
// @Summary Sync a single user
// @Description Sync a single user from auth service to LMS (requires sync secret header)
// @Tags Sync
// @Accept json
// @Produce json
// @Param X-Sync-Secret header string true "Sync secret for authentication"
// @Param request body dto.UserSyncRequest true "User sync data"
// @Success 200 {object} dto.SuccessResponse{data=dto.UserSyncResponse} "User synced successfully"
// @Failure 400 {object} dto.ErrorResponse "Invalid request"
// @Failure 401 {object} dto.ErrorResponse "Invalid sync secret"
// @Failure 500 {object} dto.ErrorResponse "Internal server error"
// @Router /sync/user [post]
func (h *UserSyncHandler) SyncUser(c *gin.Context) {
	var req dto.UserSyncRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	result, err := h.syncService.SyncUser(c.Request.Context(), &req)
	if err != nil {
		logger.Error("Failed to sync user", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("sync_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// BulkSyncUsers godoc
// @Summary Bulk sync multiple users
// @Description Sync multiple users from auth service to LMS (requires sync secret header)
// @Tags Sync
// @Accept json
// @Produce json
// @Param X-Sync-Secret header string true "Sync secret for authentication"
// @Param request body dto.BulkUserSyncRequest true "Bulk user sync data"
// @Success 200 {object} dto.SuccessResponse{data=dto.BulkUserSyncResponse} "Users synced with results"
// @Failure 400 {object} dto.ErrorResponse "Invalid request"
// @Failure 401 {object} dto.ErrorResponse "Invalid sync secret"
// @Failure 500 {object} dto.ErrorResponse "Internal server error"
// @Router /sync/users/bulk [post]
func (h *UserSyncHandler) BulkSyncUsers(c *gin.Context) {
	var req dto.BulkUserSyncRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	result, err := h.syncService.BulkSyncUsers(c.Request.Context(), &req)
	if err != nil {
		logger.Error("Failed to bulk sync users", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("sync_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// DeleteUser godoc
// @Summary Delete a user from LMS
// @Description Delete a user and all their data from LMS (requires sync secret header)
// @Tags Sync
// @Accept json
// @Produce json
// @Param X-Sync-Secret header string true "Sync secret for authentication"
// @Param userId path int true "User ID to delete"
// @Success 200 {object} dto.SuccessResponse{message=string} "User deleted from LMS"
// @Failure 400 {object} dto.ErrorResponse "Invalid user ID"
// @Failure 401 {object} dto.ErrorResponse "Invalid sync secret"
// @Failure 500 {object} dto.ErrorResponse "Internal server error"
// @Router /sync/user/{userId} [delete]
func (h *UserSyncHandler) DeleteUser(c *gin.Context) {
	userID, err := strconv.ParseInt(c.Param("userId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_user_id", "Invalid user ID"))
		return
	}

	if err := h.syncService.DeleteUser(c.Request.Context(), userID); err != nil {
		logger.Error("Failed to delete user from LMS", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("delete_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("User deleted from LMS"))
}