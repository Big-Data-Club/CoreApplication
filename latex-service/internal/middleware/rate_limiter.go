package middleware

import (
	"fmt"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"latex-service/internal/dto"
	"latex-service/pkg/cache"
)

// RateLimitByUser limits requests per authenticated user for a specific action
func RateLimitByUser(redisCache *cache.RedisCache, action string, limit int64, window time.Duration) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID, exists := c.Get("user_id")
		if !exists {
			c.Next()
			return
		}

		key := fmt.Sprintf("ratelimit:user:%v:%s", userID, action)
		count, err := redisCache.IncrementWithExpiry(c.Request.Context(), key, window)
		if err != nil {
			// Fail-open to avoid locking out users if Redis is down
			c.Next()
			return
		}

		c.Writer.Header().Set("X-RateLimit-Limit", fmt.Sprintf("%d", limit))
		c.Writer.Header().Set("X-RateLimit-Remaining", fmt.Sprintf("%d", max(0, limit-count)))
		c.Writer.Header().Set("X-RateLimit-Reset", fmt.Sprintf("%d", time.Now().Add(window).Unix()))

		if count > limit {
			c.JSON(http.StatusTooManyRequests, dto.NewErrorResponse("rate_limit_exceeded", fmt.Sprintf("Too many requests for %s. Please try again later.", action)))
			c.Abort()
			return
		}

		c.Next()
	}
}

func max(a, b int64) int64 {
	if a > b {
		return a
	}
	return b
}
