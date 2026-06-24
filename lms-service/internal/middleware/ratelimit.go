package middleware

import (
	"fmt"
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"example/hello/internal/dto"
	"example/hello/pkg/cache"
)

// isPrivateOrLocalIP checks if an IP address is a loopback or within private subnet ranges
// (RFC 1918: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16).
func isPrivateOrLocalIP(ipStr string) bool {
	ip := net.ParseIP(ipStr)
	if ip == nil {
		return false
	}
	if ip.IsLoopback() {
		return true
	}
	ip4 := ip.To4()
	if ip4 != nil {
		// 10.0.0.0/8
		if ip4[0] == 10 {
			return true
		}
		// 172.16.0.0/12 (172.16.x.x - 172.31.x.x)
		if ip4[0] == 172 && ip4[1] >= 16 && ip4[1] <= 31 {
			return true
		}
		// 192.168.0.0/16
		if ip4[0] == 192 && ip4[1] == 168 {
			return true
		}
	}
	return false
}

// RateLimit middleware limits requests per IP address
func RateLimit(redisCache *cache.RedisCache, aiSecret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Bypass rate limit for internal AI service calls
		if aiSecret != "" && c.GetHeader("X-API-Secret") == aiSecret {
			c.Next()
			return
		}

		// Bypass rate limit for health check
		if c.Request.URL.Path == "/health" {
			c.Next()
			return
		}

		// Bypass rate limit for public file serving endpoints
		if strings.HasPrefix(c.Request.URL.Path, "/api/v1/files/serve") || strings.HasPrefix(c.Request.URL.Path, "/api/v1/files/download") {
			c.Next()
			return
		}

		// Get client IP
		ip := c.ClientIP()

		// Bypass rate limit for localhost and private network/intranet IPs (e.g. frontend, VPN, campus LAN)
		if isPrivateOrLocalIP(ip) {
			c.Next()
			return
		}
		
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
		c.Writer.Header().Set("X-RateLimit-Limit", "1000")
		c.Writer.Header().Set("X-RateLimit-Remaining", fmt.Sprintf("%d", max(0, 1000-count)))
		c.Writer.Header().Set("X-RateLimit-Reset", fmt.Sprintf("%d", time.Now().Add(1*time.Minute).Unix()))

		// Check if limit exceeded
		if count > 1000 {
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