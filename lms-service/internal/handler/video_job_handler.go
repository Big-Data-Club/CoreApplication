package handler

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"
)

type VideoJobHandler struct {
	videoJobService *service.VideoJobService
}

func NewVideoJobHandler(videoJobService *service.VideoJobService) *VideoJobHandler {
	return &VideoJobHandler{
		videoJobService: videoJobService,
	}
}

// CreateVideoJob handles POST /api/v1/video-jobs
func (h *VideoJobHandler) CreateVideoJob(c *gin.Context) {
	userID := c.MustGet("user_id").(int64)
	role := c.MustGet("user_role").(string)

	var req dto.CreateVideoJobRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	result, err := h.videoJobService.CreateJob(c.Request.Context(), req, userID, role)
	if err != nil {
		logger.Error("Failed to create video job", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("creation_failed", err.Error()))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(result))
}

// GetVideoJob handles GET /api/v1/video-jobs/:jobId
func (h *VideoJobHandler) GetVideoJob(c *gin.Context) {
	userID := c.MustGet("user_id").(int64)
	role := c.MustGet("user_role").(string)
	jobID := c.Param("jobId")

	result, err := h.videoJobService.GetJob(c.Request.Context(), jobID, userID, role)
	if err != nil {
		logger.Error("Failed to get video job", err)
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// ListVideoJobs handles GET /api/v1/video-jobs?target_type=course&target_id=123
func (h *VideoJobHandler) ListVideoJobs(c *gin.Context) {
	userID := c.MustGet("user_id").(int64)
	role := c.MustGet("user_role").(string)

	targetType := c.Query("target_type")
	targetIDStr := c.Query("target_id")

	if targetType == "" || targetIDStr == "" {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", "Missing target_type or target_id query parameters"))
		return
	}

	targetID, err := strconv.ParseInt(targetIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", "Invalid target_id"))
		return
	}

	result, err := h.videoJobService.ListJobs(c.Request.Context(), targetType, targetID, userID, role)
	if err != nil {
		logger.Error("Failed to list video jobs", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("list_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// PublishVideo handles POST /api/v1/video-jobs/:jobId/publish
func (h *VideoJobHandler) PublishVideo(c *gin.Context) {
	userID := c.MustGet("user_id").(int64)
	role := c.MustGet("user_role").(string)
	jobID := c.Param("jobId")

	err := h.videoJobService.PublishVideo(c.Request.Context(), jobID, userID, role)
	if err != nil {
		logger.Error("Failed to publish video", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("publish_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(map[string]interface{}{"success": true}))
}
