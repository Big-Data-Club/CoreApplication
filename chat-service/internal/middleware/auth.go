package middleware

import (
	"net/http"
	"strings"

	"chat-service/internal/dto"
	"chat-service/pkg/logger"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

// Claims mirrors the JWT structure produced by auth-and-management-service.
type Claims struct {
	UserID int64    `json:"user_id"`
	Email  string   `json:"email"`
	Roles  []string `json:"roles"`
	jwt.RegisteredClaims
}

// Auth validates the JWT from Authorization header or authToken cookie.
// Sets ctx keys: user_id (int64), user_email (string), user_roles ([]string),
// user_role (string — primary role).
func Auth(jwtSecret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		tokenStr := extractToken(c)
		if tokenStr == "" {
			c.JSON(http.StatusUnauthorized, dto.APIResponse{
				Error: &dto.APIError{Code: "unauthorized", Message: "Missing token"},
			})
			c.Abort()
			return
		}

		claims, err := parseToken(tokenStr, jwtSecret)
		if err != nil {
			c.JSON(http.StatusUnauthorized, dto.APIResponse{
				Error: &dto.APIError{Code: "unauthorized", Message: "Invalid or expired token"},
			})
			c.Abort()
			return
		}

		if claims.UserID <= 0 {
			c.JSON(http.StatusUnauthorized, dto.APIResponse{
				Error: &dto.APIError{Code: "unauthorized", Message: "Invalid user ID in token"},
			})
			c.Abort()
			return
		}

		normalized := normalizeRoles(claims.Roles)
		primary := primaryRole(normalized)

		c.Set("user_id", claims.UserID)
		c.Set("user_email", claims.Email)
		c.Set("user_roles", normalized)
		c.Set("user_role", primary)
		c.Next()
	}
}

// RequireAdmin aborts with 403 if the caller is not ADMIN.
func RequireAdmin() gin.HandlerFunc {
	return func(c *gin.Context) {
		role, _ := c.Get("user_role")
		if role != "ADMIN" {
			c.JSON(http.StatusForbidden, dto.APIResponse{
				Error: &dto.APIError{Code: "forbidden", Message: "Admin access required"},
			})
			c.Abort()
			return
		}
		c.Next()
	}
}

// SyncSecret validates that the caller supplies the correct X-Sync-Secret header.
// Used exclusively on the /sync/* endpoints called by auth-service.
func SyncSecret(secret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		provided := c.GetHeader("X-Sync-Secret")
		if provided == "" {
			provided = c.GetHeader("X-API-Secret")
		}
		if provided != secret || secret == "" {
			c.JSON(http.StatusUnauthorized, dto.APIResponse{
				Error: &dto.APIError{Code: "unauthorized", Message: "Invalid sync secret"},
			})
			c.Abort()
			return
		}
		c.Next()
	}
}

// ParseTokenFromQuery extracts and validates a JWT from the ?token= query param.
// Used for WebSocket upgrade requests (browsers cannot set custom headers on WS).
// Returns Claims and true on success; writes HTTP error and returns false on failure.
func ParseTokenFromQuery(c *gin.Context, jwtSecret string) (*Claims, bool) {
	tokenStr := c.Query("token")
	if tokenStr == "" {
		c.JSON(http.StatusUnauthorized, dto.APIResponse{
			Error: &dto.APIError{Code: "unauthorized", Message: "Missing ?token= query parameter"},
		})
		return nil, false
	}

	claims, err := parseToken(tokenStr, jwtSecret)
	if err != nil {
		logger.Warnf("ws: invalid token: %v", err)
		c.JSON(http.StatusUnauthorized, dto.APIResponse{
			Error: &dto.APIError{Code: "unauthorized", Message: "Invalid or expired token"},
		})
		return nil, false
	}

	return claims, true
}

// ── helpers ──────────────────────────────────────────────────────────────────

func extractToken(c *gin.Context) string {
	auth := c.GetHeader("Authorization")
	if auth != "" {
		parts := strings.SplitN(auth, " ", 2)
		if len(parts) == 2 && strings.EqualFold(parts[0], "Bearer") {
			return parts[1]
		}
	}
	if cookie, err := c.Cookie("authToken"); err == nil {
		return cookie
	}
	return ""
}

func parseToken(tokenStr, secret string) (*Claims, error) {
	token, err := jwt.ParseWithClaims(tokenStr, &Claims{}, func(t *jwt.Token) (interface{}, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, jwt.ErrSignatureInvalid
		}
		return []byte(secret), nil
	})
	if err != nil {
		return nil, err
	}
	claims, ok := token.Claims.(*Claims)
	if !ok || !token.Valid {
		return nil, jwt.ErrTokenInvalidClaims
	}
	return claims, nil
}

// ExportNormalizeRoles is the public wrapper used by the WS handler when it
// needs to normalize roles extracted from the JWT outside of a Gin context.
func ExportNormalizeRoles(roles []string) []string { return normalizeRoles(roles) }

func normalizeRoles(roles []string) []string {
	out := make([]string, len(roles))
	for i, r := range roles {
		switch r {
		case "ROLE_ADMIN", "ROLE_MANAGER":
			out[i] = "ADMIN"
		case "ROLE_USER":
			out[i] = "STUDENT"
		default:
			out[i] = strings.ToUpper(r)
		}
	}
	return out
}

func primaryRole(roles []string) string {
	for _, r := range roles {
		if r == "ADMIN" {
			return "ADMIN"
		}
	}
	for _, r := range roles {
		if r == "TEACHER" {
			return "TEACHER"
		}
	}
	if len(roles) > 0 {
		return roles[0]
	}
	return "STUDENT"
}
