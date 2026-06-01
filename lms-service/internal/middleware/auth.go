package middleware

import (
	"context"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/repository"
	"example/hello/pkg/cache"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

// Claims represents JWT claims
type Claims struct {
	UserID int64    `json:"user_id"`
	Email  string   `json:"email"`
	Roles  []string `json:"roles"`
	jwt.RegisteredClaims
}

// AuthMiddleware validates JWT token and sets user info in context
func AuthMiddleware(jwtSecret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Get token from Authorization header or Cookie
		var tokenString string
		authHeader := c.GetHeader("Authorization")
		
		if authHeader != "" {
			// Check if it's a Bearer token
			parts := strings.Split(authHeader, " ")
			if len(parts) == 2 && parts[0] == "Bearer" {
				tokenString = parts[1]
			}
		}

		// Fallback to Cookie if header is missing or invalid
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

		// Validate roles is not empty
		if len(claims.Roles) == 0 {
			logger.Warn("JWT token has no roles")
			c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "No roles found in token"))
			c.Abort()
			return
		}
		
		// Normalize all roles
		normalizedRoles := make([]string, len(claims.Roles))
		for i, r := range claims.Roles {
			normalizedRoles[i] = normalizeRole(r)
		}

		// Set user info in context
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

// ServiceOrAuthMiddleware allows access via either a valid JWT OR a shared service secret
func ServiceOrAuthMiddleware(jwtSecret string, serviceSecret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		// 1. First check for Service Secret (used by AI service and other internal services)
		apiSecret := c.GetHeader("X-API-Secret")
		if apiSecret == "" {
			apiSecret = c.GetHeader("X-Sync-Secret")
		}

		if apiSecret != "" && apiSecret == serviceSecret {
			// Authorized as internal service
			userID := int64(0)
			if userIDStr := c.GetHeader("X-User-Id"); userIDStr != "" {
				if id, err := strconv.ParseInt(userIDStr, 10, 64); err == nil {
					userID = id
				}
			}
			
			c.Set("user_id", userID) 
			c.Set("user_email", "system@bdc.internal")
			c.Set("user_roles", []string{"ADMIN", "TEACHER"})
			c.Set("user_role", "ADMIN")
			c.Next()
			return
		}

		// 2. Fallback to standard JWT Auth
		// Get token from Authorization header or Cookie
		var tokenString string
		authHeader := c.GetHeader("Authorization")

		if authHeader != "" {
			// Check if it's a Bearer token
			parts := strings.Split(authHeader, " ")
			if len(parts) == 2 && parts[0] == "Bearer" {
				tokenString = parts[1]
			}
		}

		// Fallback to Cookie if header is missing or invalid
		if tokenString == "" {
			cookie, err := c.Cookie("authToken")
			if err == nil {
				tokenString = cookie
			}
		}

		if tokenString == "" {
			c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Missing authorization header, cookie, or valid service secret"))
			c.Abort()
			return
		}

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

		// Validate roles is not empty
		if len(claims.Roles) == 0 {
			logger.Warn("JWT token has no roles")
			c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "No roles found in token"))
			c.Abort()
			return
		}

		// Normalize all roles
		normalizedRoles := make([]string, len(claims.Roles))
		for i, r := range claims.Roles {
			normalizedRoles[i] = normalizeRole(r)
		}

		// Set user info in context
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

// normalizeRole converts role strings (for backward compatibility)
// Note: Roles now come from Java already normalized, so this is mainly for reference
func normalizeRole(role string) string {
	switch role {
	case "ROLE_ADMIN":
		return "ADMIN"
	case "ROLE_MANAGER":
		return "ADMIN"
	case "ROLE_USER":
		return "STUDENT"
	default:
		return strings.ToUpper(role) // Pass-through for dynamic roles
	}
}

// RequireRole checks if user has a specific role
func RequireRole(role string) gin.HandlerFunc {
	return func(c *gin.Context) {
		userRolesInterface, exists := c.Get("user_roles")
		if !exists {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "User roles not found"))
			c.Abort()
			return
		}

		userRoles, ok := userRolesInterface.([]string)
		if !ok {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Invalid user roles format"))
			c.Abort()
			return
		}

		hasRole := false
		for _, userRole := range userRoles {
			if userRole == role {
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

// RequireRoles checks if user has any of the specified roles
func RequireRoles(roles ...string) gin.HandlerFunc {
	return func(c *gin.Context) {
		userRolesInterface, exists := c.Get("user_roles")
		if !exists {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "User roles not found"))
			c.Abort()
			return
		}

		userRoles, ok := userRolesInterface.([]string)
		if !ok || len(userRoles) == 0 {
			c.JSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "Invalid user roles format"))
			c.Abort()
			return
		}

		hasRole := false
		for _, requiredRole := range roles {
			for _, userRole := range userRoles {
				if userRole == requiredRole {
					hasRole = true
					break
				}
			}
			if hasRole {
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
			// Normalize roles
			normalizedRoles := make([]string, len(claims.Roles))
			for i, r := range claims.Roles {
				normalizedRoles[i] = normalizeRole(r)
			}

			c.Set("user_id", claims.UserID)
			c.Set("user_email", claims.Email)
			c.Set("user_roles", normalizedRoles)
			// Set first role for backward compatibility
			if len(normalizedRoles) > 0 {
				c.Set("user_role", normalizedRoles[0])
			}
		}

		c.Next()
	}
}

// LoadLocalRoles loads user roles from the local database/cache and overrides the context roles.
func LoadLocalRoles(userRepo *repository.UserRepository, redisCache *cache.RedisCache) gin.HandlerFunc {
	loader := cache.NewLoader(redisCache)
	return func(c *gin.Context) {
		userIDVal, exists := c.Get("user_id")
		if !exists {
			c.Next()
			return
		}

		userID, ok := userIDVal.(int64)
		if !ok || userID <= 0 {
			c.Next()
			return
		}

		// Don't override for system/internal calls if already ADMIN
		if c.GetString("user_email") == "system@bdc.internal" {
			c.Next()
			return
		}

		// Fetch roles using cache
		roles, err := cache.GetOrLoad(c.Request.Context(), loader, cache.KeyUserRoles(userID), 5*time.Minute,
			func(ctx context.Context) ([]string, error) {
				return userRepo.GetUserRoles(ctx, userID)
			})
		if err != nil {
			logger.Warn(fmt.Sprintf("Failed to load local roles for user %d: %v", userID, err))
			c.Next()
			return
		}

		if len(roles) > 0 {
			c.Set("user_roles", roles)
			
			// Determine primary role (prefer ADMIN first, then TEACHER, then STUDENT, or first in list)
			primaryRole := roles[0]
			for _, r := range roles {
				if r == "ADMIN" {
					primaryRole = "ADMIN"
					break
				}
			}
			// If not ADMIN, check for TEACHER
			if primaryRole != "ADMIN" {
				for _, r := range roles {
					if r == "TEACHER" {
						primaryRole = "TEACHER"
						break
					}
				}
			}
			c.Set("user_role", primaryRole)
		}

		c.Next()
	}
}
