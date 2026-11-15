package handler

import (
	"context"
	"database/sql"
	"errors"
	"net/http"

	"github.com/gin-gonic/gin"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"
)

func writeQuizError(c *gin.Context, code string, err error) {
	status := http.StatusBadRequest
	message := err.Error()
	var databaseError interface{ SQLState() string }
	switch {
	case errors.Is(err, service.ErrQuizAccess):
		status = http.StatusForbidden
		message = "You do not have access to this quiz"
	case errors.Is(err, sql.ErrNoRows):
		status = http.StatusNotFound
		message = "Quiz resource not found"
	case errors.Is(err, context.DeadlineExceeded):
		status = http.StatusServiceUnavailable
		message = "Quiz operation timed out"
	case errors.As(err, &databaseError):
		status = http.StatusInternalServerError
		message = "Quiz operation failed"
		logger.Error("Quiz persistence error", err)
	}
	c.JSON(status, dto.NewErrorResponse(code, message))
}
