package handler

import (
	"net/http"
	"strconv"

	"latex-service/internal/dto"
	"latex-service/internal/service"

	"github.com/gin-gonic/gin"
)

// CommentHandler handles project comment endpoints
type CommentHandler struct {
	commentService *service.CommentService
}

// NewCommentHandler creates a new CommentHandler
func NewCommentHandler(commentService *service.CommentService) *CommentHandler {
	return &CommentHandler{commentService: commentService}
}

// Create handles POST /projects/:id/comments
func (h *CommentHandler) Create(c *gin.Context) {
	projectID, ok := parseProjectID(c)
	if !ok {
		return
	}
	userID, ok := extractUserID(c)
	if !ok {
		return
	}
	email := extractUserEmail(c)

	var req dto.CreateCommentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", err.Error()))
		return
	}

	result, err := h.commentService.CreateComment(c.Request.Context(), projectID, userID, email, &req)
	if err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("comment_failed", err.Error()))
		return
	}
	c.JSON(http.StatusCreated, dto.NewDataResponse(result))
}

// ListByProject handles GET /projects/:id/comments
func (h *CommentHandler) ListByProject(c *gin.Context) {
	projectID, ok := parseProjectID(c)
	if !ok {
		return
	}
	userID, ok := extractUserID(c)
	if !ok {
		return
	}

	result, err := h.commentService.ListByProject(c.Request.Context(), projectID, userID)
	if err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("access_denied", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// ListByFile handles GET /projects/:id/files/:fileId/comments
func (h *CommentHandler) ListByFile(c *gin.Context) {
	projectID, ok := parseProjectID(c)
	if !ok {
		return
	}
	userID, ok := extractUserID(c)
	if !ok {
		return
	}

	fileIDStr := c.Param("fileId")
	fileID, err := strconv.ParseInt(fileIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid file ID"))
		return
	}

	result, err := h.commentService.ListByFile(c.Request.Context(), projectID, fileID, userID)
	if err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("access_denied", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// Update handles PUT /projects/:id/comments/:commentId
func (h *CommentHandler) Update(c *gin.Context) {
	projectID, ok := parseProjectID(c)
	if !ok {
		return
	}
	userID, ok := extractUserID(c)
	if !ok {
		return
	}

	commentID, err := strconv.ParseInt(c.Param("commentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid comment ID"))
		return
	}

	var req dto.UpdateCommentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", err.Error()))
		return
	}

	result, err := h.commentService.UpdateComment(c.Request.Context(), projectID, commentID, userID, &req)
	if err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("update_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// Delete handles DELETE /projects/:id/comments/:commentId
func (h *CommentHandler) Delete(c *gin.Context) {
	projectID, ok := parseProjectID(c)
	if !ok {
		return
	}
	userID, ok := extractUserID(c)
	if !ok {
		return
	}

	commentID, err := strconv.ParseInt(c.Param("commentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid comment ID"))
		return
	}

	if err := h.commentService.DeleteComment(c.Request.Context(), projectID, commentID, userID); err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("delete_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Comment deleted successfully"))
}

// Resolve handles POST /projects/:id/comments/:commentId/resolve
func (h *CommentHandler) Resolve(c *gin.Context) {
	projectID, ok := parseProjectID(c)
	if !ok {
		return
	}
	userID, ok := extractUserID(c)
	if !ok {
		return
	}

	commentID, err := strconv.ParseInt(c.Param("commentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid comment ID"))
		return
	}

	if err := h.commentService.ResolveComment(c.Request.Context(), projectID, commentID, userID); err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("resolve_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Comment resolved"))
}

// Unresolve handles POST /projects/:id/comments/:commentId/unresolve
func (h *CommentHandler) Unresolve(c *gin.Context) {
	projectID, ok := parseProjectID(c)
	if !ok {
		return
	}
	userID, ok := extractUserID(c)
	if !ok {
		return
	}

	commentID, err := strconv.ParseInt(c.Param("commentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("bad_request", "Invalid comment ID"))
		return
	}

	if err := h.commentService.UnresolveComment(c.Request.Context(), projectID, commentID, userID); err != nil {
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("unresolve_failed", err.Error()))
		return
	}
	c.JSON(http.StatusOK, dto.NewMessageResponse("Comment reopened"))
}
