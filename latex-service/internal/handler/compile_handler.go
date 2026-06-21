package handler

import (
	"io"
	"net/http"
	"strconv"

	"latex-service/internal/dto"
	"latex-service/internal/service"

	"github.com/gin-gonic/gin"
)

type CompileHandler struct {
	compileService *service.CompileService
}

func NewCompileHandler(compileService *service.CompileService) *CompileHandler {
	return &CompileHandler{compileService: compileService}
}

// Compile handles initiating a compile job
func (h *CompileHandler) Compile(c *gin.Context) {
	projectIDStr := c.Param("id")
	projectID, err := strconv.ParseInt(projectIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid project ID"))
		return
	}

	var req dto.CompileRequest
	if err := c.ShouldBindJSON(&req); err != nil && c.Request.ContentLength > 0 {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", err.Error()))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	res, err := h.compileService.Compile(c.Request.Context(), userID, projectID, &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("compile_failed", err.Error()))
		return
	}

	c.JSON(http.StatusAccepted, dto.NewDataResponse(res))
}

// GetStatus handles polling compile job status
func (h *CompileHandler) GetStatus(c *gin.Context) {
	jobID := c.Param("jobId")
	if jobID == "" {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Missing job ID"))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	res, err := h.compileService.GetStatus(c.Request.Context(), userID, jobID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(res))
}

// StreamPdf streams the compiled PDF output
func (h *CompileHandler) StreamPdf(c *gin.Context) {
	jobID := c.Param("jobId")
	if jobID == "" {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Missing job ID"))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	body, size, err := h.compileService.StreamPdf(c.Request.Context(), userID, jobID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("stream_failed", err.Error()))
		return
	}
	defer body.Close()

	c.Header("Content-Type", "application/pdf")
	c.Header("Content-Disposition", "inline; filename=\"output.pdf\"")
	c.Header("Content-Length", strconv.FormatInt(size, 10))

	// Stream from MinIO directly to Gin response writer
	_, err = io.Copy(c.Writer, body)
	if err != nil {
		// Log the streaming issue but response headers are already sent
	}
}

// GetLog handles retrieving the compile log file
func (h *CompileHandler) GetLog(c *gin.Context) {
	jobID := c.Param("jobId")
	if jobID == "" {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Missing job ID"))
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, dto.NewErrorResponse("unauthorized", "Unauthorized"))
		return
	}
	userID := userIDVal.(int64)

	res, err := h.compileService.GetStatus(c.Request.Context(), userID, jobID)
	if err != nil {
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", err.Error()))
		return
	}

	logOutput := ""
	if res.LogOutput != nil {
		logOutput = *res.LogOutput
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(gin.H{"log": logOutput}))
}
