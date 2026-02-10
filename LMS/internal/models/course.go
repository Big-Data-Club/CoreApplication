package models

import (
	"database/sql"
	"time"
)

// Course represents a course in the system
type Course struct {
	ID           int64          `json:"id" db:"id"`
	Title        string         `json:"title" db:"title"`
	Description  sql.NullString `json:"description" db:"description"`
	Category     sql.NullString `json:"category" db:"category"`
	Level        sql.NullString `json:"level" db:"level"`
	ThumbnailURL sql.NullString `json:"thumbnail_url" db:"thumbnail_url"`
	Status       string         `json:"status" db:"status"`
	CreatedBy    int64          `json:"created_by" db:"created_by"`
	CreatedAt    time.Time      `json:"created_at" db:"created_at"`
	UpdatedAt    time.Time      `json:"updated_at" db:"updated_at"`
	PublishedAt  sql.NullTime   `json:"published_at" db:"published_at"`
}

// CourseWithCreator includes creator information
type CourseWithCreator struct {
	Course
	CreatorName  string `json:"creator_name" db:"creator_name"`
	CreatorEmail string `json:"creator_email" db:"creator_email"`
}

// CourseSection represents a section within a course
type CourseSection struct {
	ID          int64          `json:"id" db:"id"`
	CourseID    int64          `json:"course_id" db:"course_id"`
	Title       string         `json:"title" db:"title"`
	Description sql.NullString `json:"description" db:"description"`
	OrderIndex  int            `json:"order_index" db:"order_index"`
	IsPublished bool           `json:"is_published" db:"is_published"`
	CreatedAt   time.Time      `json:"created_at" db:"created_at"`
	UpdatedAt   time.Time      `json:"updated_at" db:"updated_at"`
}

// SectionContent represents content within a section
type SectionContent struct {
	ID          int64          `json:"id" db:"id"`
	SectionID   int64          `json:"section_id" db:"section_id"`
	Type        string         `json:"type" db:"type"`
	Title       string         `json:"title" db:"title"`
	Description sql.NullString `json:"description" db:"description"`
	OrderIndex  int            `json:"order_index" db:"order_index"`
	Metadata    []byte         `json:"metadata" db:"metadata"`
	IsPublished bool           `json:"is_published" db:"is_published"`
	IsMandatory bool           `json:"is_mandatory" db:"is_mandatory"`
	FilePath    sql.NullString `json:"file_path" db:"file_path"`
	FileSize    sql.NullInt64  `json:"file_size" db:"file_size"`
	FileType    sql.NullString `json:"file_type" db:"file_type"`
	CreatedBy   int64          `json:"created_by" db:"created_by"`
	CreatedAt   time.Time      `json:"created_at" db:"created_at"`
	UpdatedAt   time.Time      `json:"updated_at" db:"updated_at"`
}

// Course status constants
const (
	CourseStatusDraft     = "DRAFT"
	CourseStatusPublished = "PUBLISHED"
	CourseStatusArchived  = "ARCHIVED"
)

// Course level constants
const (
	CourseLevelBeginner     = "BEGINNER"
	CourseLevelIntermediate = "INTERMEDIATE"
	CourseLevelAdvanced     = "ADVANCED"
	CourseLevelAllLevels    = "ALL_LEVELS"
)

// Content type constants
const (
	ContentTypeText         = "TEXT"
	ContentTypeVideo        = "VIDEO"
	ContentTypeDocument     = "DOCUMENT"
	ContentTypeImage        = "IMAGE"
	ContentTypeQuiz         = "QUIZ"
	ContentTypeForum        = "FORUM"
	ContentTypeAnnouncement = "ANNOUNCEMENT"
)