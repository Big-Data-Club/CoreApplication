package dto

import "time"

// CreateCourseRequest represents the request to create a course
type CreateCourseRequest struct {
	Title        string `json:"title" binding:"required,min=3,max=255"`
	Description  string `json:"description" binding:"max=5000"`
	Category     string `json:"category" binding:"max=100"`
	Level        string `json:"level" binding:"omitempty,oneof=BEGINNER INTERMEDIATE ADVANCED ALL_LEVELS"`
	ThumbnailURL string `json:"thumbnail_url" binding:"omitempty,url,max=500"`
}

// UpdateCourseRequest represents the request to update a course
type UpdateCourseRequest struct {
	Title        *string `json:"title" binding:"omitempty,min=3,max=255"`
	Description  *string `json:"description" binding:"omitempty,max=5000"`
	Category     *string `json:"category" binding:"omitempty,max=100"`
	Level        *string `json:"level" binding:"omitempty,oneof=BEGINNER INTERMEDIATE ADVANCED ALL_LEVELS"`
	ThumbnailURL *string `json:"thumbnail_url" binding:"omitempty,url,max=500"`
}

// CourseResponse represents the response for a course
type CourseResponse struct {
	ID           int64     `json:"id"`
	Title        string    `json:"title"`
	Description  string    `json:"description,omitempty"`
	Category     string    `json:"category,omitempty"`
	Level        string    `json:"level,omitempty"`
	ThumbnailURL string    `json:"thumbnail_url,omitempty"`
	Status       string    `json:"status"`
	CreatedBy    int64     `json:"created_by"`
	CreatorName  string    `json:"creator_name,omitempty"`
	CreatorEmail string    `json:"creator_email,omitempty"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
	PublishedAt  *time.Time `json:"published_at,omitempty"`
}

// CreateSectionRequest represents the request to create a section
type CreateSectionRequest struct {
	Title       string `json:"title" binding:"required,min=3,max=255"`
	Description string `json:"description" binding:"max=2000"`
	OrderIndex  int    `json:"order_index" binding:"required,min=0"`
}

// UpdateSectionRequest represents the request to update a section
type UpdateSectionRequest struct {
	Title       *string `json:"title" binding:"omitempty,min=3,max=255"`
	Description *string `json:"description" binding:"omitempty,max=2000"`
	OrderIndex  *int    `json:"order_index" binding:"omitempty,min=0"`
	IsPublished *bool   `json:"is_published"`
}

// SectionResponse represents the response for a section
type SectionResponse struct {
	ID          int64     `json:"id"`
	CourseID    int64     `json:"course_id"`
	Title       string    `json:"title"`
	Description string    `json:"description,omitempty"`
	OrderIndex  int       `json:"order_index"`
	IsPublished bool      `json:"is_published"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// CreateContentRequest represents the request to create section content
type CreateContentRequest struct {
	Type        string                 `json:"type" binding:"required,oneof=TEXT VIDEO DOCUMENT IMAGE QUIZ FORUM ANNOUNCEMENT"`
	Title       string                 `json:"title" binding:"required,min=3,max=255"`
	Description string                 `json:"description" binding:"max=2000"`
	OrderIndex  int                    `json:"order_index" binding:"required,min=0"`
	Metadata    map[string]interface{} `json:"metadata"`
	IsMandatory bool                   `json:"is_mandatory"`
}

// UpdateContentRequest represents the request to update section content
type UpdateContentRequest struct {
	Title       *string                 `json:"title" binding:"omitempty,min=3,max=255"`
	Description *string                 `json:"description" binding:"omitempty,max=2000"`
	OrderIndex  *int                    `json:"order_index" binding:"omitempty,min=0"`
	Metadata    *map[string]interface{} `json:"metadata"`
	IsPublished *bool                   `json:"is_published"`
	IsMandatory *bool                   `json:"is_mandatory"`
}

// ContentResponse represents the response for section content
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