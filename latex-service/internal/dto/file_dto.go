package dto

import "time"

type FileResponse struct {
	ID          int64     `json:"id"`
	ProjectID   int64     `json:"project_id"`
	Filename    string    `json:"filename"`
	Filepath    string    `json:"filepath"`
	FileSize    int64     `json:"file_size"`
	MimeType    string    `json:"mime_type"`
	ContentHash string    `json:"content_hash,omitempty"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

type UpdateFileContentRequest struct {
	Content string `json:"content" binding:"required"`
}
