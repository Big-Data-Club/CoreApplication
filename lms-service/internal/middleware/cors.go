package middleware

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"

	"example/hello/internal/config"
)

// CORS rejects untrusted browser origins instead of merely hiding response headers.
// This also protects cookie-authenticated mutation routes from simple-form CSRF.
func CORS(cfg config.CORSConfig) gin.HandlerFunc {
	return func(c *gin.Context) {
		origin := c.GetHeader("Origin")
		allowed := false
		for _, candidate := range cfg.AllowedOrigins {
			if candidate == origin || candidate == "*" {
				allowed = true
				break
			}
		}
		if origin != "" && !allowed {
			c.AbortWithStatus(http.StatusForbidden)
			return
		}
		if origin == "" && c.GetHeader("Sec-Fetch-Site") == "cross-site" && c.Request.Method != "GET" && c.Request.Method != "HEAD" {
			c.AbortWithStatus(http.StatusForbidden)
			return
		}
		if origin != "" && allowed {
			c.Header("Access-Control-Allow-Origin", origin)
			c.Header("Vary", "Origin")
			if cfg.AllowCredentials {
				c.Header("Access-Control-Allow-Credentials", "true")
			}
		}
		c.Header("Access-Control-Allow-Methods", strings.Join(cfg.AllowedMethods, ", "))
		c.Header("Access-Control-Allow-Headers", strings.Join(cfg.AllowedHeaders, ", "))
		c.Header("Access-Control-Max-Age", "86400")
		if c.Request.Method == http.MethodOptions {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}
		c.Next()
	}
}
