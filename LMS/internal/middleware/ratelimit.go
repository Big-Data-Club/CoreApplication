package middleware

import (
	"fmt"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"example/hello/internal/dto"
	"example/hello/pkg/cache"
)

// RateLimit middleware limits requests per IP address
func RateLimit(redisCache *cache.RedisCache) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Get client IP
		ip := c.ClientIP()
		
		// Create rate limit key
		key := fmt.Sprintf("ratelimit:%s", ip)
		
		// Increment request count
		count, err := redisCache.IncrementWithExpiry(c.Request.Context(), key, 1*time.Minute)
		if err != nil {
			// If Redis is down, allow the request
			c.Next()
			return
		}

		// Set rate limit headers
		c.Writer.Header().Set("X-RateLimit-Limit", "100")
		c.Writer.Header().Set("X-RateLimit-Remaining", fmt.Sprintf("%d", max(0, 100-count)))
		c.Writer.Header().Set("X-RateLimit-Reset", fmt.Sprintf("%d", time.Now().Add(1*time.Minute).Unix()))

		// Check if limit exceeded
		if count > 100 {
			c.JSON(http.StatusTooManyRequests, dto.NewErrorResponse("rate_limit_exceeded", "Too many requests. Please try again later."))
			c.Abort()
			return
		}

		c.Next()
	}
}

// RateLimitByUser limits requests per authenticated user
func RateLimitByUser(redisCache *cache.RedisCache, limit int64, window time.Duration) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Get user ID from context
		userID, exists := c.Get("user_id")
		if !exists {
			// If not authenticated, use IP-based rate limiting
			c.Next()
			return
		}

		// Create rate limit key
		key := fmt.Sprintf("ratelimit:user:%v", userID)
		
		// Increment request count
		count, err := redisCache.IncrementWithExpiry(c.Request.Context(), key, window)
		if err != nil {
			c.Next()
			return
		}

		// Set rate limit headers
		c.Writer.Header().Set("X-RateLimit-Limit", fmt.Sprintf("%d", limit))
		c.Writer.Header().Set("X-RateLimit-Remaining", fmt.Sprintf("%d", max(0, limit-count)))
		c.Writer.Header().Set("X-RateLimit-Reset", fmt.Sprintf("%d", time.Now().Add(window).Unix()))

		// Check if limit exceeded
		if count > limit {
			c.JSON(http.StatusTooManyRequests, dto.NewErrorResponse("rate_limit_exceeded", "Too many requests. Please try again later."))
			c.Abort()
			return
		}

		c.Next()
	}
}

// max returns the maximum of two int64 values
func max(a, b int64) int64 {
	if a > b {
		return a
	}
	return b
}