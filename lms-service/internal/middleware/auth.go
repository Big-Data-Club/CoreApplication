package middleware

import (
	"context"
	"crypto/subtle"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"

	"example/hello/internal/dto"
	"example/hello/pkg/cache"
	"example/hello/pkg/logger"
)

// Claims represents JWT claims
type Claims struct {
	UserID int64    `json:"user_id"`
	Email  string   `json:"email"`
	Roles  []string `json:"roles"`
	jwt.RegisteredClaims
}

// tokenFromRequest centralizes the existing Bearer/cookie compatibility contract.
func tokenFromRequest(c *gin.Context) string {
	parts := strings.Fields(c.GetHeader("Authorization"))
	if len(parts) == 2 && parts[0] == "Bearer" {
		return parts[1]
	}
	cookie, _ := c.Cookie("authToken")
	return cookie
}

func parseClaims(raw, secret string) (*Claims, error) {
	token, err := jwt.ParseWithClaims(raw, &Claims{}, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, jwt.ErrSignatureInvalid
		}
		return []byte(secret), nil
	}, jwt.WithExpirationRequired())
	if err != nil {
		return nil, err
	}
	claims, ok := token.Claims.(*Claims)
	if !ok || !token.Valid || claims.UserID <= 0 || len(claims.Roles) == 0 {
		return nil, jwt.ErrTokenInvalidClaims
	}
	return claims, nil
}

func setClaims(c *gin.Context, claims *Claims) {
	roles := make([]string, len(claims.Roles))
	for i, role := range claims.Roles {
		roles[i] = normalizeRole(role)
	}
	primary := roles[0]
	for _, role := range roles {
		if role == "ADMIN" {
			primary = role
			break
		}
	}
	c.Set("user_authenticated", true)
	c.Set("user_id", claims.UserID)
	c.Set("user_email", claims.Email)
	c.Set("user_roles", roles)
	c.Set("user_role", primary)
}

func validServiceSecret(actual, expected string) bool {
	if expected == "" || expected == "None" || expected == "ai-service-secret-change-me" {
		return false
	}
	return subtle.ConstantTimeCompare([]byte(actual), []byte(expected)) == 1
}

// ServiceOnlyMiddleware never accepts a browser JWT as service authentication.
func ServiceOnlyMiddleware(secret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		if !validServiceSecret(c.GetHeader("X-API-Secret"), secret) {
			c.AbortWithStatusJSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Service authentication required"))
			return
		}
		c.Set("service_authenticated", true)
		c.Next()
	}
}

func AuthMiddleware(secret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		claims, err := parseClaims(tokenFromRequest(c), secret)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Invalid or expired token"))
			return
		}
		setClaims(c, claims)
		c.Next()
	}
}

// ServiceOrAuthMiddleware is reserved for explicitly delegated authoring routes.
func ServiceOrAuthMiddleware(jwtSecret, serviceSecret string) gin.HandlerFunc {
	auth := AuthMiddleware(jwtSecret)
	return func(c *gin.Context) {
		secret := c.GetHeader("X-API-Secret")
		if secret == "" {
			secret = c.GetHeader("X-Sync-Secret")
		}
		if !validServiceSecret(secret, serviceSecret) {
			auth(c)
			return
		}
		userID, _ := strconv.ParseInt(c.GetHeader("X-User-Id"), 10, 64)
		c.Set("service_authenticated", true)
		c.Set("user_id", userID)
		c.Set("user_email", "system@bdc.internal")
		c.Set("user_roles", []string{"ADMIN", "TEACHER"})
		c.Set("user_role", "ADMIN")
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
func OptionalAuth(secret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		if claims, err := parseClaims(tokenFromRequest(c), secret); err == nil {
			setClaims(c, claims)
		}
		c.Next()
	}
}

type roleReader interface {
	GetUserRoles(context.Context, int64) ([]string, error)
}

// LoadLocalRoles loads user roles from the local database/cache and overrides the context roles.
func LoadLocalRoles(userRepo roleReader, redisCache *cache.RedisCache) gin.HandlerFunc {
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
		if c.GetBool("service_authenticated") {
			c.Next()
			return
		}

		// Fetch roles using cache
		var roles []string
		var err error
		if redisCache == nil {
			roles, err = userRepo.GetUserRoles(c.Request.Context(), userID)
		} else {
			roles, err = cache.GetOrLoad(c.Request.Context(), loader, cache.KeyUserRoles(userID), 5*time.Minute, func(ctx context.Context) ([]string, error) { return userRepo.GetUserRoles(ctx, userID) })
		}

		if err != nil {
			logger.Warn(fmt.Sprintf("Failed to load local roles for user %d: %v", userID, err))
			c.AbortWithStatusJSON(http.StatusServiceUnavailable, dto.NewErrorResponse("roles_unavailable", "Authorization temporarily unavailable"))
			return
		}

		if len(roles) == 0 {
			c.AbortWithStatusJSON(http.StatusForbidden, dto.NewErrorResponse("forbidden", "No active LMS roles"))
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

// OptionalIdentity permits public reads while enriching valid user/service identity.
func OptionalIdentity(jwtSecret, serviceSecret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		if validServiceSecret(c.GetHeader("X-API-Secret"), serviceSecret) {
			c.Set("service_authenticated", true)
		}
		if claims, err := parseClaims(tokenFromRequest(c), jwtSecret); err == nil {
			setClaims(c, claims)
		}
		c.Next()
	}
}

// RequireIdentity consumes identity established by OptionalIdentity without
// reparsing JWTs and overwriting the authoritative local roles loaded afterward.
func RequireIdentity(allowService bool) gin.HandlerFunc {
	return func(c *gin.Context) {
		if !c.GetBool("user_authenticated") && !(allowService && c.GetBool("service_authenticated")) {
			c.AbortWithStatus(http.StatusUnauthorized)
			return
		}
		c.Next()
	}
}
