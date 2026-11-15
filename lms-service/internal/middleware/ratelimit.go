package middleware

import (
	"context"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"

	"example/hello/internal/dto"
	"example/hello/pkg/cache"
)

type rateCounter interface {
	IncrementWithExpiry(context.Context, string, time.Duration) (int64, error)
}

type localWindow struct {
	count   int64
	expires time.Time
}
type limiter struct {
	counter rateCounter
	mu      sync.Mutex
	windows map[string]localWindow
	now     func() time.Time
}

func newLimiter(counter rateCounter) *limiter {
	return &limiter{counter: counter, windows: make(map[string]localWindow), now: time.Now}
}

// The local fallback has a hard key cap: a Redis outage cannot create an unbounded map.
func (l *limiter) allow(c *gin.Context, key string, limit int64, window time.Duration) bool {
	var count int64
	var err error
	if l.counter != nil {
		count, err = l.counter.IncrementWithExpiry(c.Request.Context(), key, window)
	} else {
		err = fmt.Errorf("counter unavailable")
	}
	if err != nil {
		l.mu.Lock()
		now := l.now()
		entry := l.windows[key]
		if !now.Before(entry.expires) {
			if len(l.windows) >= 10000 {
				for k, v := range l.windows {
					if !now.Before(v.expires) {
						delete(l.windows, k)
					}
				}
			}
			if len(l.windows) >= 10000 {
				l.mu.Unlock()
				rejectRate(c)
				return false
			}
			entry = localWindow{expires: now.Add(window)}
		}
		entry.count++
		l.windows[key] = entry
		count = entry.count
		l.mu.Unlock()
	}
	remaining := limit - count
	if remaining < 0 {
		remaining = 0
	}
	c.Header("X-RateLimit-Limit", fmt.Sprint(limit))
	c.Header("X-RateLimit-Remaining", fmt.Sprint(remaining))
	if count > limit {
		rejectRate(c)
		return false
	}
	return true
}
func rejectRate(c *gin.Context) {
	c.Header("Retry-After", "60")
	c.AbortWithStatusJSON(http.StatusTooManyRequests, dto.NewErrorResponse("rate_limit_exceeded", "Request budget exceeded. Retry later."))
}

// RateLimit applies to public media and private proxy IPs as well as Internet clients.
func RateLimit(redis *cache.RedisCache, limit int64) gin.HandlerFunc {
	var counter rateCounter
	if redis != nil {
		counter = redis
	}
	l := newLimiter(counter)
	return func(c *gin.Context) {
		if c.Request.URL.Path != "/health" && !l.allow(c, "ratelimit:ip:"+c.ClientIP(), limit, time.Minute) {
			return
		}
		c.Next()
	}
}
func RateLimitByUser(redis *cache.RedisCache, limit, costlyLimit int64, window time.Duration) gin.HandlerFunc {
	var counter rateCounter
	if redis != nil {
		counter = redis
	}
	l := newLimiter(counter)
	return func(c *gin.Context) {
		id := c.GetInt64("user_id")
		if id <= 0 {
			c.Next()
			return
		}
		if !l.allow(c, fmt.Sprintf("ratelimit:user:%d", id), limit, window) {
			return
		}
		path := c.FullPath()
		if (strings.Contains(path, "generate") || strings.Contains(path, "upload") || strings.Contains(path, "insights")) && c.Request.Method != "GET" {
			if !l.allow(c, fmt.Sprintf("ratelimit:costly:%d", id), costlyLimit, time.Minute) {
				return
			}
		}
		c.Next()
	}
}
