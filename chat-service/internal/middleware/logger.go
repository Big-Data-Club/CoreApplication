package middleware

import (
	"time"

	"chat-service/pkg/logger"

	"github.com/gin-gonic/gin"
)

// Logger returns a Gin middleware that logs every request with method, path,
// status, latency, and client IP — structured and consistent with the service logger.
func Logger() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		path := c.Request.URL.Path
		query := c.Request.URL.RawQuery

		// Skip logging for health checks to prevent spamming
		if path == "/health" {
			c.Next()
			return
		}

		c.Next()

		latency := time.Since(start)
		status := c.Writer.Status()
		size := c.Writer.Size()
		clientIP := c.ClientIP()
		method := c.Request.Method

		if query != "" {
			path = path + "?" + query
		}

		// Choose log level based on status code
		msg := "http: %s %s %d %dms %dB ip=%s"
		switch {
		case status >= 500:
			logger.Errorf(msg, method, path, status, latency.Milliseconds(), size, clientIP)
		case status >= 400:
			logger.Warnf(msg, method, path, status, latency.Milliseconds(), size, clientIP)
		default:
			logger.Infof(msg, method, path, status, latency.Milliseconds(), size, clientIP)
		}
	}
}
