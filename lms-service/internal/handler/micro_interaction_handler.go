// lms-service/internal/handler/micro_interaction_handler.go
//
// HTTP handlers for the Quick Action Panel analytics endpoints:
//
//   POST  /api/v1/analytics/micro-interaction
//   GET   /api/v1/analytics/heatmap?course_id=...
//   GET   /api/v1/analytics/heatmap/me?course_id=...
//
// The POST endpoint is intentionally minimal - it persists a raw row
// and publishes a Kafka event. The GET endpoints read from the
// materialised mastery table maintained by the analytics worker.
package handler

import (
	"net/http"
	"strconv"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
)

type MicroInteractionHandler struct {
	svc *service.MicroInteractionService
}

func NewMicroInteractionHandler(svc *service.MicroInteractionService) *MicroInteractionHandler {
	return &MicroInteractionHandler{svc: svc}
}

// RecordInteraction godoc
// @Summary  Record a Quick Action Panel micro-interaction
// @Tags     Analytics
// @Accept   json
// @Produce  json
// @Router   /analytics/micro-interaction [post]
// @Security BearerAuth
func (h *MicroInteractionHandler) RecordInteraction(c *gin.Context) {
	var body dto.MicroInteractionRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	userID := c.MustGet("user_id").(int64)

	resp, err := h.svc.RecordInteraction(c.Request.Context(), userID, body)
	if err != nil {
		logger.Error("RecordInteraction failed", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("record_failed", err.Error()))
		return
	}

	// 202 Accepted communicates "raw log persisted, downstream
	// aggregation is asynchronous."
	c.JSON(http.StatusAccepted, dto.NewDataResponse(resp))
}

// GetHeatmap godoc
// @Summary  Get the composite mastery heatmap for a course (teacher view)
// @Tags     Analytics
// @Produce  json
// @Param    course_id query int true "Course ID"
// @Router   /analytics/heatmap [get]
// @Security BearerAuth
func (h *MicroInteractionHandler) GetHeatmap(c *gin.Context) {
	courseID, ok := parseQueryInt64(c, "course_id")
	if !ok {
		return
	}

	resp, err := h.svc.Heatmap(c.Request.Context(), courseID)
	if err != nil {
		logger.Error("Heatmap failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to compute heatmap"))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(resp))
}

// GetStudentHeatmap godoc
// @Summary  Get the composite mastery heatmap for the current student
// @Tags     Analytics
// @Produce  json
// @Param    course_id query int true "Course ID"
// @Router   /analytics/heatmap/me [get]
// @Security BearerAuth
func (h *MicroInteractionHandler) GetStudentHeatmap(c *gin.Context) {
	courseID, ok := parseQueryInt64(c, "course_id")
	if !ok {
		return
	}
	userID := c.MustGet("user_id").(int64)

	resp, err := h.svc.StudentHeatmap(c.Request.Context(), courseID, userID)
	if err != nil {
		logger.Error("StudentHeatmap failed", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("internal_error", "Failed to compute heatmap"))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(resp))
}

func parseQueryInt64(c *gin.Context, key string) (int64, bool) {
	raw := c.Query(key)
	if raw == "" {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("missing_param", key+" is required"))
		return 0, false
	}
	v, err := strconv.ParseInt(raw, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_param", key+" must be int"))
		return 0, false
	}
	return v, true
}
