package dto

import "time"

// ── Lab CRUD ────────────────────────────────────────────────────

// CreateLabRequest represents the request to create a lab.
type CreateLabRequest struct {
	Title                 string                 `json:"title" binding:"required,min=3,max=255"`
	Description           string                 `json:"description" binding:"max=5000"`
	Category              string                 `json:"category" binding:"max=100"`
	Level                 string                 `json:"level" binding:"omitempty,oneof=BEGINNER INTERMEDIATE ADVANCED ALL_LEVELS"`
	ThumbnailURL          string                 `json:"thumbnail_url" binding:"omitempty,max=500"`
	LabType               string                 `json:"lab_type" binding:"required,oneof=CODING HPC JUPYTER WORKSPACE DATABASE CUSTOM"`
	RuntimeConfig         map[string]interface{} `json:"runtime_config"`
	MaxSessionDurationMin int                    `json:"max_session_duration_min" binding:"omitempty,min=1,max=1440"`
	MaxConcurrentSessions int                    `json:"max_concurrent_sessions" binding:"omitempty,min=1,max=1000"`
	MaxSubmissions        *int                   `json:"max_submissions"`
	AutoGrade             bool                   `json:"auto_grade"`
	GradingConfig         map[string]interface{} `json:"grading_config"`
	StartTime             *time.Time             `json:"start_time"`
	Deadline              *time.Time             `json:"deadline"`
	AllowLateSubmission   bool                   `json:"allow_late_submission"`
	LatePenaltyPercent    int                    `json:"late_penalty_percent" binding:"omitempty,min=0,max=100"`
}

// UpdateLabRequest represents the request to update a lab.
type UpdateLabRequest struct {
	Title                 *string                 `json:"title" binding:"omitempty,min=3,max=255"`
	Description           *string                 `json:"description" binding:"omitempty,max=5000"`
	Category              *string                 `json:"category" binding:"omitempty,max=100"`
	Level                 *string                 `json:"level" binding:"omitempty,oneof=BEGINNER INTERMEDIATE ADVANCED ALL_LEVELS"`
	ThumbnailURL          *string                 `json:"thumbnail_url" binding:"omitempty,max=500"`
	RuntimeConfig         *map[string]interface{} `json:"runtime_config"`
	MaxSessionDurationMin *int                    `json:"max_session_duration_min" binding:"omitempty,min=1,max=1440"`
	MaxConcurrentSessions *int                    `json:"max_concurrent_sessions" binding:"omitempty,min=1,max=1000"`
	MaxSubmissions        *int                    `json:"max_submissions"`
	AutoGrade             *bool                   `json:"auto_grade"`
	GradingConfig         *map[string]interface{} `json:"grading_config"`
	StartTime             *time.Time              `json:"start_time"`
	Deadline              *time.Time              `json:"deadline"`
	AllowLateSubmission   *bool                   `json:"allow_late_submission"`
	LatePenaltyPercent    *int                    `json:"late_penalty_percent" binding:"omitempty,min=0,max=100"`
}

// LabResponse represents the response for a lab.
type LabResponse struct {
	ID                    int64                  `json:"id"`
	Title                 string                 `json:"title"`
	Description           string                 `json:"description,omitempty"`
	Category              string                 `json:"category,omitempty"`
	Level                 string                 `json:"level,omitempty"`
	ThumbnailURL          string                 `json:"thumbnail_url,omitempty"`
	LabType               string                 `json:"lab_type"`
	Status                string                 `json:"status"`
	RuntimeConfig         map[string]interface{} `json:"runtime_config,omitempty"`
	MaxSessionDurationMin int                    `json:"max_session_duration_min"`
	MaxConcurrentSessions int                    `json:"max_concurrent_sessions"`
	MaxSubmissions        *int                   `json:"max_submissions,omitempty"`
	AutoGrade             bool                   `json:"auto_grade"`
	GradingConfig         map[string]interface{} `json:"grading_config,omitempty"`
	StartTime             *time.Time             `json:"start_time,omitempty"`
	Deadline              *time.Time             `json:"deadline,omitempty"`
	AllowLateSubmission   bool                   `json:"allow_late_submission"`
	LatePenaltyPercent    int                    `json:"late_penalty_percent"`
	CreatedBy             int64                  `json:"created_by"`
	CreatorName           string                 `json:"creator_name,omitempty"`
	CreatorEmail          string                 `json:"creator_email,omitempty"`
	PublishedAt           *time.Time             `json:"published_at,omitempty"`
	CreatedAt             time.Time              `json:"created_at"`
	UpdatedAt             time.Time              `json:"updated_at"`
	EnrollmentCount       int                    `json:"enrollment_count"`
}

// ── Lab Sections ────────────────────────────────────────────────

type CreateSectionRequest struct {
	Title       string `json:"title" binding:"required,min=3,max=255"`
	Description string `json:"description" binding:"max=2000"`
	OrderIndex  int    `json:"order_index" binding:"min=0"`
}

type UpdateSectionRequest struct {
	Title       *string `json:"title" binding:"omitempty,min=3,max=255"`
	Description *string `json:"description" binding:"omitempty,max=2000"`
	OrderIndex  *int    `json:"order_index" binding:"omitempty,min=0"`
	IsPublished *bool   `json:"is_published"`
}

type SectionResponse struct {
	ID          int64     `json:"id"`
	LabID       int64     `json:"lab_id"`
	Title       string    `json:"title"`
	Description string    `json:"description,omitempty"`
	OrderIndex  int       `json:"order_index"`
	IsPublished bool      `json:"is_published"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// ── Lab Section Content ─────────────────────────────────────────

type CreateContentRequest struct {
	Type        string                 `json:"type" binding:"required,oneof=TEXT DOCUMENT IMAGE CODE_TEMPLATE CHECKPOINT"`
	Title       string                 `json:"title" binding:"required,min=3,max=255"`
	Description string                 `json:"description" binding:"max=2000"`
	OrderIndex  int                    `json:"order_index" binding:"min=0"`
	Metadata    map[string]interface{} `json:"metadata"`
	IsMandatory bool                   `json:"is_mandatory"`
}

type UpdateContentRequest struct {
	Title       *string                 `json:"title" binding:"omitempty,min=3,max=255"`
	Description *string                 `json:"description" binding:"omitempty,max=2000"`
	OrderIndex  *int                    `json:"order_index" binding:"omitempty,min=0"`
	Metadata    *map[string]interface{} `json:"metadata"`
	IsPublished *bool                   `json:"is_published"`
	IsMandatory *bool                   `json:"is_mandatory"`
}

type ContentResponse struct {
	ID          int64                  `json:"id"`
	SectionID   int64                  `json:"section_id"`
	Type        string                 `json:"type"`
	Title       string                 `json:"title"`
	Description string                 `json:"description,omitempty"`
	OrderIndex  int                    `json:"order_index"`
	Metadata    map[string]interface{} `json:"metadata,omitempty"`
	IsPublished bool                   `json:"is_published"`
	IsMandatory bool                   `json:"is_mandatory"`
	FilePath    string                 `json:"file_path,omitempty"`
	FileSize    int64                  `json:"file_size,omitempty"`
	FileType    string                 `json:"file_type,omitempty"`
	CreatedBy   int64                  `json:"created_by"`
	CreatedAt   time.Time              `json:"created_at"`
	UpdatedAt   time.Time              `json:"updated_at"`
}

// ── Lab Link Info (cross-service) ───────────────────────────────

type LabLinkInfo struct {
	ID          int64  `json:"id"`
	Title       string `json:"title"`
	LabType     string `json:"lab_type"`
	Level       string `json:"level"`
	Status      string `json:"status"`
	Category    string `json:"category"`
	Description string `json:"description"`
}
