package middleware

import (
	"context"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"

	"example/hello/internal/config"
)

// RequestBudget is an admission limit, not a waiting queue. Full capacity sheds load
// before HTTP handlers allocate uploads or wait for database connections.
func RequestBudget(uploadBytes int64, limits config.RequestLimits) gin.HandlerFunc {
	regular := make(chan struct{}, limits.Requests)
	uploads := make(chan struct{}, limits.Uploads)
	streams := make(chan struct{}, limits.Streams)
	costly := make(chan struct{}, limits.Costly)
	callbacks := make(chan struct{}, limits.Callbacks)
	return func(c *gin.Context) {
		path := c.FullPath()
		if path == "" {
			path = c.Request.URL.Path
		}
		if path == "/health" {
			c.Next()
			return
		}
		slots := regular
		timeout := 15 * time.Second
		bodyLimit := int64(2 << 20)
		switch {
		case strings.HasSuffix(path, "/stream"):
			slots = streams
			timeout = 5 * time.Minute
		case strings.Contains(c.GetHeader("Content-Type"), "multipart/form-data"):
			slots = uploads
			timeout = 2 * time.Minute
			bodyLimit = uploadBytes + (1 << 20)
		case strings.Contains(path, "/internal/"):
			slots = callbacks
			bodyLimit = 16 << 20
			timeout = 30 * time.Second
		case strings.Contains(path, "generate") || strings.Contains(path, "/ai/") || strings.Contains(path, "bulk-grade"):
			slots = costly
			timeout = 2 * time.Minute
		case strings.Contains(path, "/files/"):
			timeout = 5 * time.Minute
		}
		select {
		case slots <- struct{}{}:
			defer func() { <-slots }()
		default:
			c.Header("Retry-After", "5")
			c.AbortWithStatus(http.StatusServiceUnavailable)
			return
		}
		c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, bodyLimit)
		ctx, cancel := context.WithTimeout(c.Request.Context(), timeout)
		defer cancel()
		c.Request = c.Request.WithContext(ctx)
		c.Next()
	}
}

// LimitStreamsPerUser is installed after JWT authentication. A single user cannot
// occupy every global SSE slot; entries disappear when their last stream closes.
func LimitStreamsPerUser(maximum int) gin.HandlerFunc {
	var mu sync.Mutex
	active := make(map[int64]int)
	return func(c *gin.Context) {
		if !strings.HasSuffix(c.Request.URL.Path, "/stream") {
			c.Next()
			return
		}
		userID := c.GetInt64("user_id")
		if userID <= 0 {
			c.AbortWithStatus(http.StatusUnauthorized)
			return
		}
		mu.Lock()
		if active[userID] >= maximum {
			mu.Unlock()
			c.Header("Retry-After", "5")
			c.AbortWithStatus(http.StatusTooManyRequests)
			return
		}
		active[userID]++
		mu.Unlock()
		defer func() {
			mu.Lock()
			active[userID]--
			if active[userID] == 0 {
				delete(active, userID)
			}
			mu.Unlock()
		}()
		c.Next()
	}
}
