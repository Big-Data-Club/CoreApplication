package handler

import (
	"context"
	"errors"
	"net/http"

	"github.com/gin-gonic/gin"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"
)

type fileAccess interface {
	Register(context.Context, string, int64, int64, bool) error
	Forget(context.Context, string) error
	Authorize(context.Context, string, int64, string, bool, bool) error
}

func (h *FileHandler) authorizeFile(c *gin.Context, path string, write bool) bool {
	if h.access == nil {
		c.AbortWithStatus(http.StatusServiceUnavailable)
		return false
	}
	err := h.access.Authorize(c.Request.Context(), path, c.GetInt64("user_id"), c.GetString("user_role"), c.GetBool("service_authenticated"), write)
	if err == nil {
		return true
	}
	if errors.Is(err, service.ErrFileAccess) {
		c.AbortWithStatusJSON(http.StatusNotFound, dto.NewErrorResponse("file_not_found", "File not found"))
	} else {
		logger.Error("File authorization failed", err)
		c.AbortWithStatus(http.StatusServiceUnavailable)
	}
	return false
}
