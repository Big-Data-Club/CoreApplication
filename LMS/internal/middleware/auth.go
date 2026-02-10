package middleware

import (
	"fmt"
	"net/http"
	"strings"

	"example/hello/internal/dto"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

// Claims represents JWT claims
type Claims struct {
	UserID int64  `json:"user_id"`
	Email  string `json:"email"`
	Role   string `json:"role"`
	jwt.RegisteredClaims
}

// AuthMiddleware validates JWT token and sets user info in context
func AuthMiddleware(jwtSecret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Get token from Authorization header
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Missing authorization header"))
			c.Abort()
			return
		}

		// Check if it's a Bearer token
		parts := strings.Split(authHeader, " ")
		if len(parts) != 2 || parts[0] != "Bearer" {
			c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Invalid authorization header format"))
			c.Abort()
			return
		}

		tokenString := parts[1]

		// Parse and validate token
		token, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(token *jwt.Token) (interface{}, error) {
			// Validate signing method
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

		// Extract claims
		claims, ok := token.Claims.(*Claims)
		if !ok || !token.Valid {
			c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Invalid token claims"))
			c.Abort()
			return
		}

		// Validate user_id is not empty
		if claims.UserID <= 0 {
			logger.Warn(fmt.Sprintf("JWT token has invalid or missing user_id: %d", claims.UserID))
			c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "User ID not found in token"))
			c.Abort()
			return
		}

		// Normalize role: ROLE_ADMIN -> ADMIN, ROLE_USER -> STUDENT, etc
		normalizedRole := normalizeRole(claims.Role)
		if normalizedRole == "" {
			logger.Warn(fmt.Sprintf("JWT token has unknown role: %s", claims.Role))
			normalizedRole = "STUDENT" // Default to STUDENT
		}
		
		// Set user info in context
		c.Set("user_id", claims.UserID)
		c.Set("user_email", claims.Email)
		c.Set("user_role", normalizedRole)

		c.Next()
	}
}

// normalizeRole converts Spring backend roles (ROLE_ADMIN) to LMS roles (ADMIN)
func normalizeRole(role string) string {
	switch role {
	case "ROLE_ADMIN":
		return "ADMIN"
	case "ROLE_MANAGER":
		return "ADMIN"
	case "ROLE_USER":
		return "STUDENT"
	case "ADMIN":
		return "ADMIN"
	case "TEACHER":
		return "TEACHER"
	case "STUDENT":
		return "STUDENT"
	default:
		return ""
	}
}

// RequireRole checks if user has a specific role
func RequireRole(role string) gin.HandlerFunc {
	return func(c *gin.Context) {
		userRole, exists := c.Get("user_role")
		if !exists {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "User role not found"))
			c.Abort()
			return
		}

		if userRole.(string) != role {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Insufficient permissions"))
			c.Abort()
			return
		}

		c.Next()
	}
}

// RequireRoles checks if user has any of the specified roles
func RequireRoles(roles ...string) gin.HandlerFunc {
	return func(c *gin.Context) {
		userRole, exists := c.Get("user_role")
		if !exists {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "User role not found"))
			c.Abort()
			return
		}

		role := userRole.(string)
		hasRole := false
		for _, r := range roles {
			if role == r {
				hasRole = true
				break
			}
		}

		if !hasRole {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Insufficient permissions"))
			c.Abort()
			return
		}

		c.Next()
	}
}

// OptionalAuth is similar to AuthMiddleware but doesn't abort if token is missing
func OptionalAuth(jwtSecret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			c.Next()
			return
		}

		parts := strings.Split(authHeader, " ")
		if len(parts) != 2 || parts[0] != "Bearer" {
			c.Next()
			return
		}

		tokenString := parts[1]
		token, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(token *jwt.Token) (interface{}, error) {
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, jwt.ErrSignatureInvalid
			}
			return []byte(jwtSecret), nil
		})

		if err != nil {
			c.Next()
			return
		}

		if claims, ok := token.Claims.(*Claims); ok && token.Valid {
			c.Set("user_id", claims.UserID)
			c.Set("user_email", claims.Email)
			c.Set("user_role", claims.Role)
		}

		c.Next()
	}
}
