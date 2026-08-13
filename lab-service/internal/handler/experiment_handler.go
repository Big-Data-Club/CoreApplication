package handler

import (
	"errors"
	"net/http"
	"strconv"

	"lab-service/internal/dto"
	"lab-service/internal/service"

	"github.com/gin-gonic/gin"
)

type ExperimentHandler struct {
	experimentService *service.ExperimentService
}

func NewExperimentHandler(experimentService *service.ExperimentService) *ExperimentHandler {
	return &ExperimentHandler{experimentService: experimentService}
}

func (h *ExperimentHandler) CreateVersion(c *gin.Context) {
	labID, ok := positiveID(c, "labId")
	if !ok {
		return
	}
	var req dto.CreateLabVersionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	version, status, err := h.experimentService.CreateVersion(
		c.Request.Context(), labID, c.GetInt64("user_id"), c.GetString("user_role"), &req,
	)
	if err != nil {
		var validationErr *service.DefinitionValidationError
		if errors.As(err, &validationErr) {
			c.JSON(status, gin.H{
				"success": false,
				"error":   "definition_validation_error",
				"message": err.Error(),
				"issues":  validationErr.Issues,
			})
			return
		}
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewSuccessResponse("Lab version created", version))
}

func (h *ExperimentHandler) GetVersion(c *gin.Context) {
	versionID, ok := positiveID(c, "versionId")
	if !ok {
		return
	}
	version, status, err := h.experimentService.GetVersion(
		c.Request.Context(), versionID, c.GetInt64("user_id"), c.GetString("user_role"),
	)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewDataResponse(version))
}

func (h *ExperimentHandler) ValidateVersion(c *gin.Context) {
	versionID, ok := positiveID(c, "versionId")
	if !ok {
		return
	}
	result, status, err := h.experimentService.ValidateVersion(
		c.Request.Context(), versionID, c.GetInt64("user_id"), c.GetString("user_role"),
	)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewDataResponse(result))
}

func (h *ExperimentHandler) PublishVersion(c *gin.Context) {
	versionID, ok := positiveID(c, "versionId")
	if !ok {
		return
	}
	status, err := h.experimentService.PublishVersion(
		c.Request.Context(), versionID, c.GetInt64("user_id"), c.GetString("user_role"),
	)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewMessageResponse("Lab version published"))
}

func (h *ExperimentHandler) CreateRun(c *gin.Context) {
	versionID, ok := positiveID(c, "versionId")
	if !ok {
		return
	}
	var req dto.CreateRunRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	run, status, err := h.experimentService.CreateRun(
		c.Request.Context(), versionID, c.GetInt64("user_id"), c.GetString("user_role"), &req,
	)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewSuccessResponse("Lab run started", run))
}

func (h *ExperimentHandler) GetRun(c *gin.Context) {
	runID, ok := positiveID(c, "runId")
	if !ok {
		return
	}
	run, status, err := h.experimentService.GetRun(
		c.Request.Context(), runID, c.GetInt64("user_id"), c.GetString("user_role"),
	)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewDataResponse(run))
}

func (h *ExperimentHandler) ListLabRuns(c *gin.Context) {
	labID, ok := positiveID(c, "labId")
	if !ok {
		return
	}
	page, err := strconv.Atoi(c.DefaultQuery("page", "1"))
	if err != nil || page < 1 {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_page", "page must be a positive integer"))
		return
	}
	pageSize, err := strconv.Atoi(c.DefaultQuery("page_size", "20"))
	if err != nil || pageSize < 1 || pageSize > 100 {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_page_size", "page_size must be between 1 and 100"))
		return
	}
	response, status, err := h.experimentService.ListLabRuns(
		c.Request.Context(), labID, c.GetInt64("user_id"), c.GetString("user_role"),
		c.Query("status"), page, pageSize,
	)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, response)
}

func (h *ExperimentHandler) CreateTrial(c *gin.Context) {
	runID, ok := positiveID(c, "runId")
	if !ok {
		return
	}
	var req dto.CreateTrialRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	trial, status, err := h.experimentService.CreateTrial(
		c.Request.Context(), runID, c.GetInt64("user_id"), &req,
	)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewSuccessResponse("Experiment trial created", trial))
}

func (h *ExperimentHandler) AppendEvidence(c *gin.Context) {
	runID, ok := positiveID(c, "runId")
	if !ok {
		return
	}
	var req dto.AppendEvidenceRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	event, status, err := h.experimentService.AppendEvidence(
		c.Request.Context(), runID, c.GetInt64("user_id"), &req,
	)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewSuccessResponse("Evidence appended", event))
}

func (h *ExperimentHandler) ListEvidence(c *gin.Context) {
	runID, ok := positiveID(c, "runId")
	if !ok {
		return
	}
	afterSeq, err := strconv.ParseInt(c.DefaultQuery("after_seq", "0"), 10, 64)
	if err != nil || afterSeq < 0 {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_after_seq", "after_seq must be a non-negative integer"))
		return
	}
	limit, err := strconv.Atoi(c.DefaultQuery("limit", "200"))
	if err != nil || limit < 1 || limit > 500 {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_limit", "limit must be between 1 and 500"))
		return
	}
	events, status, err := h.experimentService.ListEvidence(
		c.Request.Context(), runID, c.GetInt64("user_id"), c.GetString("user_role"), afterSeq, limit,
	)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewDataResponse(events))
}

func positiveID(c *gin.Context, param string) (int64, bool) {
	id, err := strconv.ParseInt(c.Param(param), 10, 64)
	if err != nil || id <= 0 {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "invalid "+param))
		return 0, false
	}
	return id, true
}
