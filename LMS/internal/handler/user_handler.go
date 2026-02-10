package handler

import (
	"net/http"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
)

type UserHandler struct {
	userService *service.UserService
}

func NewUserHandler(userService *service.UserService) *UserHandler {
	return &UserHandler{
		userService: userService,
	}
}

// GetMyRoles godoc
// @Summary Get my roles
// @Description Get the roles of the authenticated user
// @Tags User
// @Accept json
// @Produce json
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.UserRolesResponse} "User roles retrieved successfully"
// @Failure 401 {object} dto.ErrorResponse "Unauthorized - user not authenticated"
// @Failure 500 {object} dto.ErrorResponse "Internal server error"
// @Router /me/roles [get]
func (h *UserHandler) GetMyRoles(c *gin.Context) {
	// Get user info from context (set by auth middleware)
	userID, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "User not authenticated"))
		return
	}

	email, exists := c.Get("user_email")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "User email not found"))
		return
	}

	// Get user roles
	roles, err := h.userService.GetMyRoles(c.Request.Context(), userID.(int64), email.(string))
	if err != nil {
		logger.Error("Failed to get user roles", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to retrieve user roles"))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(roles))
}