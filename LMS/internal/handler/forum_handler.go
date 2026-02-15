package handler

import (
	"net/http"
	"strconv"

	"example/hello/internal/dto"
	"example/hello/internal/service"
	"example/hello/pkg/logger"

	"github.com/gin-gonic/gin"
)

type ForumHandler struct {
	forumService *service.ForumService
}

func NewForumHandler(forumService *service.ForumService) *ForumHandler {
	return &ForumHandler{
		forumService: forumService,
	}
}

// ============================================
// POST ENDPOINTS
// ============================================

// CreatePost godoc
// @Summary Create a forum post
// @Description Create a new post in a forum
// @Tags Forum
// @Accept json
// @Produce json
// @Param contentId path int true "Content ID"
// @Param post body dto.CreateForumPostRequest true "Post data"
// @Security BearerAuth
// @Success 201 {object} dto.SuccessResponse{data=dto.ForumPostResponse}
// @Failure 400 {object} dto.ErrorResponse
// @Failure 401 {object} dto.ErrorResponse
// @Router /content/{contentId}/forum/posts [post]
func (h *ForumHandler) CreatePost(c *gin.Context) {
	contentID, err := strconv.ParseInt(c.Param("contentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid content ID"))
		return
	}

	userID, _ := c.Get("user_id")

	var req dto.CreateForumPostRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	post, err := h.forumService.CreatePost(c.Request.Context(), contentID, userID.(int64), &req)
	if err != nil {
		logger.Error("Failed to create post", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("create_failed", err.Error()))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(post))
}

// ListPosts godoc
// @Summary List forum posts
// @Description Get all posts in a forum with sorting and filtering
// @Tags Forum
// @Accept json
// @Produce json
// @Param contentId path int true "Content ID"
// @Param sort_by query string false "Sort by (votes, newest, oldest, views)" default(newest)
// @Param search query string false "Search in title and body"
// @Param tags query string false "Filter by tags (comma-separated)"
// @Param page query int false "Page number" default(1)
// @Param limit query int false "Items per page" default(20)
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.ListResponse}
// @Failure 400 {object} dto.ErrorResponse
// @Router /content/{contentId}/forum/posts [get]
func (h *ForumHandler) ListPosts(c *gin.Context) {
	contentID, err := strconv.ParseInt(c.Param("contentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid content ID"))
		return
	}

	userID, _ := c.Get("user_id")

	var req dto.ListForumPostsRequest
	if err := c.ShouldBindQuery(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	result, err := h.forumService.ListPosts(c.Request.Context(), contentID, userID.(int64), &req)
	if err != nil {
		logger.Error("Failed to list posts", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("list_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// GetPost godoc
// @Summary Get a forum post
// @Description Get a single post by ID
// @Tags Forum
// @Accept json
// @Produce json
// @Param postId path int true "Post ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.ForumPostResponse}
// @Failure 400 {object} dto.ErrorResponse
// @Failure 404 {object} dto.ErrorResponse
// @Router /forum/posts/{postId} [get]
func (h *ForumHandler) GetPost(c *gin.Context) {
	postID, err := strconv.ParseInt(c.Param("postId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid post ID"))
		return
	}

	userID, _ := c.Get("user_id")

	post, err := h.forumService.GetPost(c.Request.Context(), postID, userID.(int64))
	if err != nil {
		logger.Error("Failed to get post", err)
		c.JSON(http.StatusNotFound, dto.NewErrorResponse("not_found", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(post))
}

// UpdatePost godoc
// @Summary Update a forum post
// @Description Update a post (owner only)
// @Tags Forum
// @Accept json
// @Produce json
// @Param postId path int true "Post ID"
// @Param post body dto.UpdateForumPostRequest true "Updated post data"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.ForumPostResponse}
// @Failure 400 {object} dto.ErrorResponse
// @Failure 403 {object} dto.ErrorResponse
// @Router /forum/posts/{postId} [put]
func (h *ForumHandler) UpdatePost(c *gin.Context) {
	postID, err := strconv.ParseInt(c.Param("postId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid post ID"))
		return
	}

	userID, _ := c.Get("user_id")

	var req dto.UpdateForumPostRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	post, err := h.forumService.UpdatePost(c.Request.Context(), postID, userID.(int64), &req)
	if err != nil {
		logger.Error("Failed to update post", err)
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("update_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(post))
}

// DeletePost godoc
// @Summary Delete a forum post
// @Description Delete a post (owner or admin)
// @Tags Forum
// @Accept json
// @Produce json
// @Param postId path int true "Post ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse
// @Failure 400 {object} dto.ErrorResponse
// @Failure 403 {object} dto.ErrorResponse
// @Router /forum/posts/{postId} [delete]
func (h *ForumHandler) DeletePost(c *gin.Context) {
	postID, err := strconv.ParseInt(c.Param("postId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid post ID"))
		return
	}

	userID, _ := c.Get("user_id")
	roles, _ := c.Get("user_roles")
	isAdmin := containsRole(roles.([]string), "ADMIN")

	err = h.forumService.DeletePost(c.Request.Context(), postID, userID.(int64), isAdmin)
	if err != nil {
		logger.Error("Failed to delete post", err)
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("delete_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Post deleted successfully"))
}

// PinPost godoc
// @Summary Pin/unpin a forum post
// @Description Pin or unpin a post (teacher/admin only)
// @Tags Forum
// @Accept json
// @Produce json
// @Param postId path int true "Post ID"
// @Param request body dto.PinPostRequest true "Pin request"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse
// @Failure 400 {object} dto.ErrorResponse
// @Failure 403 {object} dto.ErrorResponse
// @Router /forum/posts/{postId}/pin [post]
func (h *ForumHandler) PinPost(c *gin.Context) {
	postID, err := strconv.ParseInt(c.Param("postId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid post ID"))
		return
	}

	var req dto.PinPostRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	err = h.forumService.PinPost(c.Request.Context(), postID, req.IsPinned)
	if err != nil {
		logger.Error("Failed to pin post", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("pin_failed", err.Error()))
		return
	}

	message := "Post pinned successfully"
	if !req.IsPinned {
		message = "Post unpinned successfully"
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse(message))
}

// LockPost godoc
// @Summary Lock/unlock a forum post
// @Description Lock or unlock a post (teacher/admin only)
// @Tags Forum
// @Accept json
// @Produce json
// @Param postId path int true "Post ID"
// @Param request body dto.LockPostRequest true "Lock request"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse
// @Failure 400 {object} dto.ErrorResponse
// @Failure 403 {object} dto.ErrorResponse
// @Router /forum/posts/{postId}/lock [post]
func (h *ForumHandler) LockPost(c *gin.Context) {
	postID, err := strconv.ParseInt(c.Param("postId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid post ID"))
		return
	}

	var req dto.LockPostRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	err = h.forumService.LockPost(c.Request.Context(), postID, req.IsLocked)
	if err != nil {
		logger.Error("Failed to lock post", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("lock_failed", err.Error()))
		return
	}

	message := "Post locked successfully"
	if !req.IsLocked {
		message = "Post unlocked successfully"
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse(message))
}

// ============================================
// COMMENT ENDPOINTS
// ============================================

// CreateComment godoc
// @Summary Create a comment
// @Description Create a comment on a post or reply to another comment
// @Tags Forum
// @Accept json
// @Produce json
// @Param postId path int true "Post ID"
// @Param comment body dto.CreateForumCommentRequest true "Comment data"
// @Security BearerAuth
// @Success 201 {object} dto.SuccessResponse{data=dto.ForumCommentResponse}
// @Failure 400 {object} dto.ErrorResponse
// @Router /forum/posts/{postId}/comments [post]
func (h *ForumHandler) CreateComment(c *gin.Context) {
	postID, err := strconv.ParseInt(c.Param("postId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid post ID"))
		return
	}

	userID, _ := c.Get("user_id")

	var req dto.CreateForumCommentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	comment, err := h.forumService.CreateComment(c.Request.Context(), postID, userID.(int64), &req)
	if err != nil {
		logger.Error("Failed to create comment", err)
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("create_failed", err.Error()))
		return
	}

	c.JSON(http.StatusCreated, dto.NewDataResponse(comment))
}

// ListComments godoc
// @Summary List comments
// @Description Get all comments for a post (nested tree structure)
// @Tags Forum
// @Accept json
// @Produce json
// @Param postId path int true "Post ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=[]dto.ForumCommentResponse}
// @Failure 400 {object} dto.ErrorResponse
// @Router /forum/posts/{postId}/comments [get]
func (h *ForumHandler) ListComments(c *gin.Context) {
	postID, err := strconv.ParseInt(c.Param("postId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid post ID"))
		return
	}

	userID, _ := c.Get("user_id")

	comments, err := h.forumService.ListComments(c.Request.Context(), postID, userID.(int64))
	if err != nil {
		logger.Error("Failed to list comments", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("list_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(comments))
}

// UpdateComment godoc
// @Summary Update a comment
// @Description Update a comment (owner only)
// @Tags Forum
// @Accept json
// @Produce json
// @Param commentId path int true "Comment ID"
// @Param comment body dto.UpdateForumCommentRequest true "Updated comment data"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.ForumCommentResponse}
// @Failure 400 {object} dto.ErrorResponse
// @Failure 403 {object} dto.ErrorResponse
// @Router /forum/comments/{commentId} [put]
func (h *ForumHandler) UpdateComment(c *gin.Context) {
	commentID, err := strconv.ParseInt(c.Param("commentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid comment ID"))
		return
	}

	userID, _ := c.Get("user_id")

	var req dto.UpdateForumCommentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	comment, err := h.forumService.UpdateComment(c.Request.Context(), commentID, userID.(int64), &req)
	if err != nil {
		logger.Error("Failed to update comment", err)
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("update_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(comment))
}

// DeleteComment godoc
// @Summary Delete a comment
// @Description Delete a comment (owner or admin)
// @Tags Forum
// @Accept json
// @Produce json
// @Param commentId path int true "Comment ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse
// @Failure 400 {object} dto.ErrorResponse
// @Failure 403 {object} dto.ErrorResponse
// @Router /forum/comments/{commentId} [delete]
func (h *ForumHandler) DeleteComment(c *gin.Context) {
	commentID, err := strconv.ParseInt(c.Param("commentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid comment ID"))
		return
	}

	userID, _ := c.Get("user_id")
	roles, _ := c.Get("user_roles")
	isAdmin := containsRole(roles.([]string), "ADMIN")

	err = h.forumService.DeleteComment(c.Request.Context(), commentID, userID.(int64), isAdmin)
	if err != nil {
		logger.Error("Failed to delete comment", err)
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("delete_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Comment deleted successfully"))
}

// AcceptComment godoc
// @Summary Accept a comment as answer
// @Description Mark a comment as accepted answer (post owner or teacher/admin)
// @Tags Forum
// @Accept json
// @Produce json
// @Param commentId path int true "Comment ID"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse
// @Failure 400 {object} dto.ErrorResponse
// @Failure 403 {object} dto.ErrorResponse
// @Router /forum/comments/{commentId}/accept [post]
func (h *ForumHandler) AcceptComment(c *gin.Context) {
	commentID, err := strconv.ParseInt(c.Param("commentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid comment ID"))
		return
	}

	userID, _ := c.Get("user_id")
	roles, _ := c.Get("user_roles")
	isTeacherOrAdmin := containsRole(roles.([]string), "TEACHER") || containsRole(roles.([]string), "ADMIN")

	err = h.forumService.AcceptComment(c.Request.Context(), commentID, userID.(int64), isTeacherOrAdmin)
	if err != nil {
		logger.Error("Failed to accept comment", err)
		c.JSON(http.StatusForbidden, dto.NewErrorResponse("accept_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewMessageResponse("Comment accepted as answer"))
}

// ============================================
// VOTE ENDPOINTS
// ============================================

// VotePost godoc
// @Summary Vote on a post
// @Description Upvote or downvote a post
// @Tags Forum
// @Accept json
// @Produce json
// @Param postId path int true "Post ID"
// @Param vote body dto.VoteRequest true "Vote data"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.VoteResponse}
// @Failure 400 {object} dto.ErrorResponse
// @Router /forum/posts/{postId}/vote [post]
func (h *ForumHandler) VotePost(c *gin.Context) {
	postID, err := strconv.ParseInt(c.Param("postId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid post ID"))
		return
	}

	userID, _ := c.Get("user_id")

	var req dto.VoteRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	result, err := h.forumService.VotePost(c.Request.Context(), postID, userID.(int64), req.VoteType)
	if err != nil {
		logger.Error("Failed to vote on post", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("vote_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// VoteComment godoc
// @Summary Vote on a comment
// @Description Upvote or downvote a comment
// @Tags Forum
// @Accept json
// @Produce json
// @Param commentId path int true "Comment ID"
// @Param vote body dto.VoteRequest true "Vote data"
// @Security BearerAuth
// @Success 200 {object} dto.SuccessResponse{data=dto.VoteResponse}
// @Failure 400 {object} dto.ErrorResponse
// @Router /forum/comments/{commentId}/vote [post]
func (h *ForumHandler) VoteComment(c *gin.Context) {
	commentID, err := strconv.ParseInt(c.Param("commentId"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_id", "Invalid comment ID"))
		return
	}

	userID, _ := c.Get("user_id")

	var req dto.VoteRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, dto.NewErrorResponse("invalid_request", err.Error()))
		return
	}

	result, err := h.forumService.VoteComment(c.Request.Context(), commentID, userID.(int64), req.VoteType)
	if err != nil {
		logger.Error("Failed to vote on comment", err)
		c.JSON(http.StatusInternalServerError, dto.NewErrorResponse("vote_failed", err.Error()))
		return
	}

	c.JSON(http.StatusOK, dto.NewDataResponse(result))
}

// Helper function
func containsRole(roles []string, role string) bool {
	for _, r := range roles {
		if r == role {
			return true
		}
	}
	return false
}