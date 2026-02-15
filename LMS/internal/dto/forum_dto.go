package dto

import "time"

// ============================================
// FORUM POST DTOs
// ============================================

// CreateForumPostRequest represents the request to create a forum post
type CreateForumPostRequest struct {
	Title string   `json:"title" binding:"required,min=5,max=255"`
	Body  string   `json:"body" binding:"required,min=10"`
	Tags  []string `json:"tags" binding:"omitempty,max=5,dive,max=50"`
}

// UpdateForumPostRequest represents the request to update a forum post
type UpdateForumPostRequest struct {
	Title *string   `json:"title" binding:"omitempty,min=5,max=255"`
	Body  *string   `json:"body" binding:"omitempty,min=10"`
	Tags  *[]string `json:"tags" binding:"omitempty,max=5,dive,max=50"`
}

// ForumPostResponse represents the response for a forum post
type ForumPostResponse struct {
	ID              int64     `json:"id"`
	ContentID       int64     `json:"content_id"`
	UserID          int64     `json:"user_id"`
	UserName        string    `json:"user_name"`
	UserEmail       string    `json:"user_email"`
	Title           string    `json:"title"`
	Body            string    `json:"body"`
	Tags            []string  `json:"tags"`
	Upvotes         int       `json:"upvotes"`
	Downvotes       int       `json:"downvotes"`
	Score           int       `json:"score"` // upvotes - downvotes
	CommentCount    int       `json:"comment_count"`
	ViewCount       int       `json:"view_count"`
	IsPinned        bool      `json:"is_pinned"`
	IsLocked        bool      `json:"is_locked"`
	CurrentUserVote *string   `json:"current_user_vote,omitempty"` // "upvote", "downvote", or null
	CreatedAt       time.Time `json:"created_at"`
	UpdatedAt       time.Time `json:"updated_at"`
}

// ListForumPostsRequest represents query parameters for listing posts
type ListForumPostsRequest struct {
	SortBy string `form:"sort_by" binding:"omitempty,oneof=votes newest oldest views"`
	Search string `form:"search"`
	Tags   string `form:"tags"` // comma-separated tags
	Page   int    `form:"page" binding:"omitempty,min=1"`
	Limit  int    `form:"limit" binding:"omitempty,min=1,max=100"`
}

// ============================================
// FORUM COMMENT DTOs
// ============================================

// CreateForumCommentRequest represents the request to create a comment
type CreateForumCommentRequest struct {
	Body            string  `json:"body" binding:"required,min=1"`
	ParentCommentID *int64  `json:"parent_comment_id"`
}

// UpdateForumCommentRequest represents the request to update a comment
type UpdateForumCommentRequest struct {
	Body *string `json:"body" binding:"omitempty,min=1"`
}

// ForumCommentResponse represents the response for a forum comment
type ForumCommentResponse struct {
	ID              int64                   `json:"id"`
	PostID          int64                   `json:"post_id"`
	ParentCommentID *int64                  `json:"parent_comment_id"`
	UserID          int64                   `json:"user_id"`
	UserName        string                  `json:"user_name"`
	UserEmail       string                  `json:"user_email"`
	Body            string                  `json:"body"`
	Upvotes         int                     `json:"upvotes"`
	Downvotes       int                     `json:"downvotes"`
	Score           int                     `json:"score"`
	IsAccepted      bool                    `json:"is_accepted"`
	Depth           int                     `json:"depth"`
	CurrentUserVote *string                 `json:"current_user_vote,omitempty"`
	Replies         []*ForumCommentResponse `json:"replies,omitempty"`
	CreatedAt       time.Time               `json:"created_at"`
	UpdatedAt       time.Time               `json:"updated_at"`
}

// ============================================
// FORUM VOTE DTOs
// ============================================

// VoteRequest represents the request to vote
type VoteRequest struct {
	VoteType string `json:"vote_type" binding:"required,oneof=upvote downvote"`
}

// VoteResponse represents the vote response
type VoteResponse struct {
	Success    bool   `json:"success"`
	VoteType   string `json:"vote_type"`
	NewScore   int    `json:"new_score"`
	Upvotes    int    `json:"upvotes"`
	Downvotes  int    `json:"downvotes"`
}

// ============================================
// ADMIN ACTIONS
// ============================================

// PinPostRequest represents request to pin/unpin a post
type PinPostRequest struct {
	IsPinned bool `json:"is_pinned"`
}

// LockPostRequest represents request to lock/unlock a post
type LockPostRequest struct {
	IsLocked bool `json:"is_locked"`
}

// AcceptCommentRequest represents request to accept a comment as answer
type AcceptCommentRequest struct {
	IsAccepted bool `json:"is_accepted"`
}