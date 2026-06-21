package dto

import "time"

type CompileRequest struct {
	Compiler string `json:"compiler" binding:"omitempty,oneof=pdflatex xelatex lualatex"`
}

type CompileResponse struct {
	JobID     string `json:"job_id"`
	ProjectID int64  `json:"project_id"`
	Status    string `json:"status"`
}

type CompileStatusResponse struct {
	JobID        string     `json:"job_id"`
	ProjectID    int64      `json:"project_id"`
	UserID       int64      `json:"user_id"`
	Compiler     string     `json:"compiler"`
	Status       string     `json:"status"`
	PdfPath      *string    `json:"pdf_path,omitempty"`
	LogOutput    *string    `json:"log_output,omitempty"`
	ErrorMessage *string    `json:"error_message,omitempty"`
	DurationMs   *int       `json:"duration_ms,omitempty"`
	CreatedAt    time.Time  `json:"created_at"`
	CompletedAt  *time.Time `json:"completed_at,omitempty"`
}
