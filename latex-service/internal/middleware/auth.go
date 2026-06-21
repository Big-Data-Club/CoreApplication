package middleware

import (
	"fmt"
	"net/http"
	"strings"

	"latex-service/internal/dto"
	"latex-service/pkg/logger"

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
			logger.Warn(fmt.Sprintf("JWT token has invalid or missing user_id: %d", claims.UserID))
			c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "User ID not found in token"))
			c.Abort()
			return
		}

		// Normalize roles
		var normalizedRoles []string
		for _, r := range claims.Roles {
			role := strings.ToUpper(strings.TrimSpace(r))
			if strings.HasPrefix(role, "ROLE_") {
				role = strings.TrimPrefix(role, "ROLE_")
			}
			normalizedRoles = append(normalizedRoles, role)
		}

		if len(normalizedRoles) == 0 {
			normalizedRoles = []string{"USER"}
		}

		primaryRole := normalizedRoles[0]
		for _, r := range normalizedRoles {
			if r == "ADMIN" {
				primaryRole = "ADMIN"
				break
			}
		}

		c.Set("user_id", claims.UserID)
		c.Set("user_email", claims.Email)
		c.Set("user_roles", normalizedRoles)
		c.Set("user_role", primaryRole)

		c.Next()
	}
}
