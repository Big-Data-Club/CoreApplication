package middleware

import (
	"strings"

	"github.com/gin-gonic/gin"
)

// NoCache middleware sets Cache-Control headers to prevent client-side caching of API responses
func NoCache() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Uploaded filenames are immutable and file handlers provide their own
		// long-lived cache headers. Do not attach contradictory Pragma/Expires
		// headers, otherwise browsers may download the same PDF again.
		if strings.HasPrefix(c.Request.URL.Path, "/api/v1/files/serve/") ||
			strings.HasPrefix(c.Request.URL.Path, "/api/v1/files/download/") {
			c.Next()
			return
		}

		c.Header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
		c.Header("Pragma", "no-cache")
		c.Header("Expires", "0")
		c.Next()
	}
}
