package handler

import (
	"database/sql"
	"errors"
	"net/http"

	"github.com/gin-gonic/gin"

	"example/hello/internal/dto"
	"example/hello/internal/repository"
	"example/hello/pkg/logger"
)

func writeCallbackError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, repository.ErrCallbackScope):
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("scope_mismatch", "Callback does not match job"))
	case errors.Is(err, repository.ErrCallbackConflict):
		c.JSON(http.StatusConflict, dto.NewErrorResponse("callback_conflict", "Result already saved"))
	case errors.Is(err, sql.ErrNoRows):
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", "Job not found"))
	default:
		logger.Error("Callback persistence failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("callback_failed", "Could not save callback"))
	}
}

func validCallbackStatus(status string, progress int) bool {
	if progress < 0 || progress > 100 {
		return false
	}
	switch status {
	case "queued", "processing", "completed", "failed":
		return true
	}
	return false
}
