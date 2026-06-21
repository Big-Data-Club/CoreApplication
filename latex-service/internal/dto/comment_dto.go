package dto

import "time"

// CreateCommentRequest is the request body for creating a comment on a file
type CreateCommentRequest struct {
	FileID         int64   `json:"file_id"          binding:"required"`
	Content        string  `json:"content"          binding:"required,min=1,max=5000"`
	SelectionStart *int    `json:"selection_start"`
	SelectionEnd   *int    `json:"selection_end"`
	SelectedText   *string `json:"selected_text"`
	ParentID       *int64  `json:"parent_id"`
}

// UpdateCommentRequest is the request body for editing a comment
type UpdateCommentRequest struct {
	Content string `json:"content" binding:"required,min=1,max=5000"`
}

// CommentResponse is the response body for a comment record
type CommentResponse struct {
	ID             int64              `json:"id"`
	ProjectID      int64              `json:"project_id"`
	FileID         int64              `json:"file_id"`
	UserID         int64              `json:"user_id"`
	UserEmail      string             `json:"user_email"`
	Content        string             `json:"content"`
	SelectionStart *int               `json:"selection_start,omitempty"`
	SelectionEnd   *int               `json:"selection_end,omitempty"`
	SelectedText   *string            `json:"selected_text,omitempty"`
	ParentID       *int64             `json:"parent_id,omitempty"`
	Resolved       bool               `json:"resolved"`
	ResolvedBy     *int64             `json:"resolved_by,omitempty"`
	ResolvedAt     *time.Time         `json:"resolved_at,omitempty"`
	Replies        []*CommentResponse `json:"replies,omitempty"`
	CreatedAt      time.Time          `json:"created_at"`
	UpdatedAt      time.Time          `json:"updated_at"`
}
