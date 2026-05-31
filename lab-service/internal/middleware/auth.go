package middleware

import (
	"fmt"
	"net/http"
	"strings"

	"lab-service/internal/dto"
	"lab-service/pkg/logger"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

// Claims represents JWT claims.
type Claims struct {
	UserID int64    `json:"user_id"`
	Email  string   `json:"email"`
	Roles  []string `json:"roles"`
	jwt.RegisteredClaims
}

// AuthMiddleware validates JWT token and sets user info in context.
func AuthMiddleware(jwtSecret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		var tokenString string
		authHeader := c.GetHeader("Authorization")

		if authHeader != "" {
			parts := strings.Split(authHeader, " ")
			if len(parts) == 2 && parts[0] == "Bearer" {
				tokenString = parts[1]
			}
		}

		if tokenString == "" {
			cookie, err := c.Cookie("authToken")
			if err == nil {
				tokenString = cookie
			}
		}

		if tokenString == "" {
			c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Missing authorization header or cookie"))
			c.Abort()
			return
		}

		token, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(token *jwt.Token) (interface{}, error) {
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, jwt.ErrSignatureInvalid
			}
			return []byte(jwtSecret), nil
		})

		if err != nil {
			c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Invalid or expired token"))
			c.Abort()
			return
		}

		claims, ok := token.Claims.(*Claims)
		if !ok || !token.Valid {
			c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Invalid token claims"))
			c.Abort()
			return
		}

		if claims.UserID <= 0 {
			logger.Warn(fmt.Sprintf("JWT token has invalid user_id: %d", claims.UserID))
			c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "User ID not found in token"))
			c.Abort()
			return
		}

		if len(claims.Roles) == 0 {
			c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "No roles found in token"))
			c.Abort()
			return
		}

		normalizedRoles := make([]string, len(claims.Roles))
		for i, r := range claims.Roles {
			normalizedRoles[i] = normalizeRole(r)
		}

		c.Set("user_id", claims.UserID)
		c.Set("user_email", claims.Email)
		c.Set("user_roles", normalizedRoles)

		primaryRole := normalizedRoles[0]
		for _, r := range normalizedRoles {
			if r == "ADMIN" {
				primaryRole = "ADMIN"
				break
			}
		}
		c.Set("user_role", primaryRole)
		c.Next()
	}
}

// ServiceOrAuthMiddleware allows access via JWT or shared service secret.
func ServiceOrAuthMiddleware(jwtSecret string, serviceSecret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		apiSecret := c.GetHeader("X-API-Secret")
		if apiSecret == "" {
			apiSecret = c.GetHeader("X-Sync-Secret")
		}

		if apiSecret != "" && apiSecret == serviceSecret {
			c.Set("user_id", int64(0))
			c.Set("user_email", "system@bdc.internal")
			c.Set("user_roles", []string{"ADMIN", "TEACHER"})
			c.Set("user_role", "ADMIN")
			c.Next()
			return
		}

		// Fallback to JWT
		AuthMiddleware(jwtSecret)(c)
	}
}

func normalizeRole(role string) string {
	switch role {
	case "ROLE_ADMIN", "ROLE_MANAGER":
		return "ADMIN"
	case "ROLE_USER":
		return "STUDENT"
	default:
		return strings.ToUpper(role)
	}
}

// RequireRoles checks if user has any of the specified roles.
func RequireRoles(roles ...string) gin.HandlerFunc {
	return func(c *gin.Context) {
		userRolesI, exists := c.Get("user_roles")
		if !exists {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "User roles not found"))
			c.Abort()
			return
		}

		userRoles, ok := userRolesI.([]string)
		if !ok || len(userRoles) == 0 {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Invalid user roles format"))
			c.Abort()
			return
		}

		for _, required := range roles {
			for _, has := range userRoles {
				if has == required {
					c.Next()
					return
				}
			}
		}

		c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Insufficient permissions"))
		c.Abort()
	}
}
