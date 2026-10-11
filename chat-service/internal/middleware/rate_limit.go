package middleware

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/redis/go-redis/v9"
)

// Shared fixed windows bound authenticated HTTP traffic across replicas.
// Reads and mutations have separate budgets, so polling cannot consume sends.
const chatRateScript = `local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], 60) end
return count`

type rateCounter func(context.Context, string) (int64, error)

func ChatRateLimit(rdb *redis.Client, reads, writes int) gin.HandlerFunc {
	return chatRateLimit(func(ctx context.Context, key string) (int64, error) {
		return rdb.Eval(ctx, chatRateScript, []string{key}).Int64()
	}, reads, writes)
}

func chatRateLimit(count rateCounter, reads, writes int) gin.HandlerFunc {
	return func(c *gin.Context) {
		limit, kind := writes, "write"
		if c.Request.Method == http.MethodGet || c.Request.Method == http.MethodHead {
			limit, kind = reads, "read"
		}
		if limit < 1 {
			limit = 120
		}
		ctx, cancel := context.WithTimeout(c.Request.Context(), time.Second)
		defer cancel()
		value, err := count(ctx, fmt.Sprintf("chat:rate:%s:%d", kind, c.GetInt64("user_id")))
		if err != nil {
			c.AbortWithStatusJSON(http.StatusServiceUnavailable, gin.H{"error": "Chat is temporarily busy. Please retry."})
			return
		}
		if value > int64(limit) {
			c.Header("Retry-After", "60")
			c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{"error": "Too many chat requests. Please wait before retrying."})
			return
		}
		c.Next()
	}
}
