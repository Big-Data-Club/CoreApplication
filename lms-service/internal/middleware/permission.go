package middleware

import (
	"net/http"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
)

// RequirePermission returns a Gin middleware that checks whether the current
// user's primary role has the specified permission code.
// ADMIN always passes (super-admin bypass handled inside PermissionService).
func RequirePermission(permService *service.PermissionService, code string) gin.HandlerFunc {
	return func(c *gin.Context) {
		roleName := c.GetString("user_role")
		if roleName == "" {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "No role in context"))
			c.Abort()
			return
		}

		allowed, err := permService.CheckPermission(c.Request.Context(), roleName, code)
		if err != nil {
			logger.Warn("Permission check error: " + err.Error())
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Permission check failed"))
			c.Abort()
			return
		}

		if !allowed {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden",
				"You do not have the required permission: "+code))
			c.Abort()
			return
		}

		c.Next()
	}
}
