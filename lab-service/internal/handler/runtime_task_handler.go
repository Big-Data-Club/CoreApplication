package handler

import (
	"github.com/gin-gonic/gin"
	"lab-service/internal/dto"
	"lab-service/internal/service"
	"net/http"
	"strconv"
)

type RuntimeTaskHandler struct{ s *service.RuntimeTaskService }

func NewRuntimeTaskHandler(s *service.RuntimeTaskService) *RuntimeTaskHandler {
	return &RuntimeTaskHandler{s: s}
}
func (h *RuntimeTaskHandler) Create(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	var req dto.CreateRuntimeTaskRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	out, status, err := h.s.Create(c.Request.Context(), id, req)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("task_error", err.Error()))
		return
	}
	c.JSON(status, dto.NewDataResponse(out))
}
func (h *RuntimeTaskHandler) Delete(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("taskId"), 10, 64)
	status, err := h.s.Delete(c.Request.Context(), id)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("task_error", err.Error()))
		return
	}
	c.JSON(status, dto.NewMessageResponse("Task deleted"))
}
func (h *RuntimeTaskHandler) Progress(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	out, status, err := h.s.Progress(c.Request.Context(), labID, c.GetInt64("user_id"))
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("task_error", err.Error()))
		return
	}
	c.JSON(status, dto.NewDataResponse(out))
}
func (h *RuntimeTaskHandler) Check(c *gin.Context) {
	labID, _ := strconv.ParseInt(c.Param("labId"), 10, 64)
	var req dto.CheckRuntimeTasksRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("validation_error", err.Error()))
		return
	}
	out, status, err := h.s.Check(c.Request.Context(), labID, c.GetInt64("user_id"), req.SessionID)
	if err != nil {
		c.JSON(status, dto.NewErrorResponse("task_error", err.Error()))
		return
	}
	c.JSON(status, dto.NewDataResponse(out))
}
