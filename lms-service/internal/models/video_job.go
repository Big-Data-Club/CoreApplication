package models

import (
	"database/sql"
	"time"
)

// Video generation job statuses
const (
	VideoJobStatusPending    = "PENDING"
	VideoJobStatusPlanning   = "PLANNING"
	VideoJobStatusScripting  = "SCRIPTING"
	VideoJobStatusRendering  = "RENDERING"
	VideoJobStatusUploading  = "UPLOADING"
	VideoJobStatusCompleted  = "COMPLETED"
	VideoJobStatusPublishing = "PUBLISHING"
	VideoJobStatusPublic     = "PUBLIC"
	VideoJobStatusFailed     = "FAILED"
	VideoJobStatusCancelled  = "CANCELLED"
)

// Video visibility statuses
const (
	VideoVisibilityUnlisted = "unlisted"
	VideoVisibilityPublic   = "public"
)

type VideoGenerationJob struct {
	ID               string         `json:"id" db:"id"`
	TargetType       string         `json:"target_type" db:"target_type"`
	TargetID         int64          `json:"target_id" db:"target_id"`
	CustomPrompt     sql.NullString `json:"custom_prompt" db:"custom_prompt"`
	Language         string         `json:"language" db:"language"`
	TemplateType     string         `json:"template_type" db:"template_type"`
	CreatedBy        int64          `json:"created_by" db:"created_by"`
	Status           string         `json:"status" db:"status"`
	Progress         int            `json:"progress" db:"progress"`
	RetryCount       int            `json:"retry_count" db:"retry_count"`
	MaxRetries       int            `json:"max_retries" db:"max_retries"`
	LastErrorMessage sql.NullString `json:"last_error_message" db:"last_error_message"`
	LastErrorAt      sql.NullTime   `json:"last_error_at" db:"last_error_at"`
	YoutubeVideoID   sql.NullString `json:"youtube_video_id" db:"youtube_video_id"`
	YoutubeURL       sql.NullString `json:"youtube_url" db:"youtube_url"`
	Visibility       string         `json:"visibility" db:"visibility"`
	CreatedAt        time.Time      `json:"created_at" db:"created_at"`
	UpdatedAt        time.Time      `json:"updated_at" db:"updated_at"`
}
