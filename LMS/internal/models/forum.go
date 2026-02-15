package models

import (
	"database/sql"
	"time"
)

// ForumPost represents a forum post
type ForumPost struct {
	ID           int64          `json:"id" db:"id"`
	ContentID    int64          `json:"content_id" db:"content_id"`
	UserID       int64          `json:"user_id" db:"user_id"`
	Title        string         `json:"title" db:"title"`
	Body         string         `json:"body" db:"body"`
	Tags         []string       `json:"tags" db:"tags"`
	Upvotes      int            `json:"upvotes" db:"upvotes"`
	Downvotes    int            `json:"downvotes" db:"downvotes"`
	CommentCount int            `json:"comment_count" db:"comment_count"`
	ViewCount    int            `json:"view_count" db:"view_count"`
	IsPinned     bool           `json:"is_pinned" db:"is_pinned"`
	IsLocked     bool           `json:"is_locked" db:"is_locked"`
	CreatedAt    time.Time      `json:"created_at" db:"created_at"`
	UpdatedAt    time.Time      `json:"updated_at" db:"updated_at"`
}

// ForumPostWithUser includes user information
type ForumPostWithUser struct {
	ForumPost
	UserName      string `json:"user_name" db:"user_name"`
	UserEmail     string `json:"user_email" db:"user_email"`
	CurrentUserVote sql.NullString `json:"current_user_vote" db:"current_user_vote"`
}

// ForumComment represents a comment on a forum post
type ForumComment struct {
	ID              int64          `json:"id" db:"id"`
	PostID          int64          `json:"post_id" db:"post_id"`
	ParentCommentID sql.NullInt64  `json:"parent_comment_id" db:"parent_comment_id"`
	UserID          int64          `json:"user_id" db:"user_id"`
	Body            string         `json:"body" db:"body"`
	Upvotes         int            `json:"upvotes" db:"upvotes"`
	Downvotes       int            `json:"downvotes" db:"downvotes"`
	IsAccepted      bool           `json:"is_accepted" db:"is_accepted"`
	Depth           int            `json:"depth" db:"depth"`
	CreatedAt       time.Time      `json:"created_at" db:"created_at"`
	UpdatedAt       time.Time      `json:"updated_at" db:"updated_at"`
}

// ForumCommentWithUser includes user information and replies
type ForumCommentWithUser struct {
	ForumComment
	UserName        string                  `json:"user_name" db:"user_name"`
	UserEmail       string                  `json:"user_email" db:"user_email"`
	CurrentUserVote sql.NullString          `json:"current_user_vote" db:"current_user_vote"`
	Replies         []*ForumCommentWithUser `json:"replies,omitempty"`
}

// ForumVote represents a vote on a post or comment
type ForumVote struct {
	ID          int64     `json:"id" db:"id"`
	UserID      int64     `json:"user_id" db:"user_id"`
	VotableType string    `json:"votable_type" db:"votable_type"`
	VotableID   int64     `json:"votable_id" db:"votable_id"`
	VoteType    string    `json:"vote_type" db:"vote_type"`
	CreatedAt   time.Time `json:"created_at" db:"created_at"`
}

// Vote type constants
const (
	VoteTypeUpvote   = "upvote"
	VoteTypeDownvote = "downvote"
)

// Votable type constants
const (
	VotableTypePost    = "post"
	VotableTypeComment = "comment"
)

// Sort options
const (
	SortByVotes   = "votes"
	SortByNewest  = "newest"
	SortByOldest  = "oldest"
	SortByViews   = "views"
)