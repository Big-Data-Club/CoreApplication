package middleware

import (
	"time"
	"fmt"

	"github.com/gin-gonic/gin"
	"example/hello/pkg/logger"
)

// Logger middleware logs HTTP requests
func Logger() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Start timer
		start := time.Now()
		path := c.Request.URL.Path
		query := c.Request.URL.RawQuery

		// Process request
		c.Next()

		// Calculate latency
		latency := time.Since(start)
		
		// Get status code
		status := c.Writer.Status()
		
		// Get client IP
		clientIP := c.ClientIP()
		
		// Get method
		method := c.Request.Method
		
		// Get user agent
		userAgent := c.Request.UserAgent()
		
		// Get error if any
		errorMessage := c.Errors.ByType(gin.ErrorTypePrivate).String()

		// Build log message
		logData := map[string]interface{}{
			"status":     status,
			"method":     method,
			"path":       path,
			"query":      query,
			"ip":         clientIP,
			"user_agent": userAgent,
			"latency":    latency.Milliseconds(),
		}

		// Add user ID if authenticated
		if userID, exists := c.Get("user_id"); exists {
			logData["user_id"] = userID
		}

		// Add error if exists
		if errorMessage != "" {
			logData["error"] = errorMessage
		}

		// Log based on status code
		if status >= 500 {
			logger.ErrorWithFields("Server error", logData)
		} else if status >= 400 {
			logger.WarnWithFields("Client error", logData)
		} else {
			logger.InfoWithFields("Request completed", logData)
		}
	}
}

// RequestID middleware adds a unique request ID to each request
func RequestID() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Get request ID from header or generate new one
		requestID := c.GetHeader("X-Request-ID")
		if requestID == "" {
			requestID = generateRequestID()
		}

		// Set request ID in context and response header
		c.Set("request_id", requestID)
		c.Writer.Header().Set("X-Request-ID", requestID)

		c.Next()
	}
}

// generateRequestID generates a unique request ID
func generateRequestID() string {
	// Simple timestamp-based ID
	return fmt.Sprintf("%d", time.Now().UnixNano())
}

// Recovery middleware with custom logging
func Recovery() gin.HandlerFunc {
	return func(c *gin.Context) {
		defer func() {
			if err := recover(); err != nil {
				// Log the panic
				logger.ErrorWithFields("Panic recovered", map[string]interface{}{
					"error":      err,
					"path":       c.Request.URL.Path,
					"method":     c.Request.Method,
					"ip":         c.ClientIP(),
					"user_agent": c.Request.UserAgent(),
				})

				// Return error response
				c.JSON(500, gin.H{
					"success": false,
					"error":   "internal_server_error",
					"message": "An internal error occurred",
				})
				c.Abort()
			}
		}()

		c.Next()
	}
}
