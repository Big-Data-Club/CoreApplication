package dto

import "time"

type CreateVideoJobRequest struct {
	TargetType   string `json:"target_type"   binding:"required,oneof=course section"`
	TargetID     int64  `json:"target_id"     binding:"required"`
	CustomPrompt string `json:"custom_prompt" binding:"omitempty,max=5000"`
	Language     string `json:"language"      binding:"omitempty,oneof=vi en"`
	TemplateType string `json:"template_type" binding:"omitempty,oneof=dark light"`
}

type VideoJobResponse struct {
	ID               string    `json:"id"`
	TargetType       string    `json:"target_type"`
	TargetID         int64     `json:"target_id"`
	CustomPrompt     string    `json:"custom_prompt,omitempty"`
	Language         string    `json:"language"`
	TemplateType     string    `json:"template_type"`
	CreatedBy        int64     `json:"created_by"`
	Status           string    `json:"status"`
	Progress         int       `json:"progress"`
	RetryCount       int       `json:"retry_count"`
	LastErrorMessage string    `json:"last_error_message,omitempty"`
	YoutubeVideoID   string    `json:"youtube_video_id,omitempty"`
	YoutubeURL       string    `json:"youtube_url,omitempty"`
	Visibility       string    `json:"visibility"`
	PreviewURL       string    `json:"preview_url,omitempty"`
	CreatedAt        time.Time `json:"created_at"`
	UpdatedAt        time.Time `json:"updated_at"`
}

type VideoJobListResponse struct {
	Jobs       []VideoJobResponse `json:"jobs"`
	TotalCount int                `json:"total_count"`
}
