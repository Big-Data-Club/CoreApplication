package handler

import (
	"net/http"
	"strconv"

	"lab-service/internal/dto"
	"lab-service/internal/service"

	"github.com/gin-gonic/gin"
)

type SubmissionHandler struct {
	subService *service.SubmissionService
}

func NewSubmissionHandler(subService *service.SubmissionService) *SubmissionHandler {
	return &SubmissionHandler{subService: subService}
}

// RunCode runs submitted code against sample tests only (not graded).
func (h *SubmissionHandler) RunCode(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	var req dto.RunCodeRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	userID := c.GetInt64("user_id")
	resp, status, err := h.subService.RunCode(c.Request.Context(), labID, userID, &req)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewDataResponse(resp))
}

// SubmitCode submits code for grading against all tests.
func (h *SubmissionHandler) SubmitCode(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	var req dto.SubmitCodeRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	userID := c.GetInt64("user_id")
	resp, status, err := h.subService.SubmitCode(c.Request.Context(), labID, userID, &req)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewDataResponse(resp))
}

// GetSubmission returns a submission with detailed results.
func (h *SubmissionHandler) GetSubmission(c *gin.Context) {
	subID, _ := strconv.ParseInt(c.Param("subId"), 10, 64)
	resp, status, err := h.subService.GetSubmission(c.Request.Context(), subID)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, dto.NewDataResponse(resp))
}

// ListMySubmissions returns the user's submissions for a lab.
func (h *SubmissionHandler) ListMySubmissions(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	userID := c.GetInt64("user_id")
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))

	resp, status, err := h.subService.ListMySubmissions(c.Request.Context(), labID, userID, page, pageSize)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("error", err.Error()))
		return
	}
	c.JSON(status, resp)
}
