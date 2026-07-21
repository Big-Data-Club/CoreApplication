package middleware

import (
	"github.com/gin-gonic/gin"
)

// NoCache middleware sets Cache-Control headers to prevent client-side caching of API responses
func NoCache() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
		c.Header("Pragma", "no-cache")
		c.Header("Expires", "0")
		c.Next()
	}
}
