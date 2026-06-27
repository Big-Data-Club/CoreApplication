package models

import (
	"database/sql"
	"encoding/json"
	"time"
)

// Micro quiz job statuses (reuse same lifecycle as micro lesson jobs)
const (
	MicroQuizJobStatusQueued     = "queued"
	MicroQuizJobStatusProcessing = "processing"
	MicroQuizJobStatusCompleted  = "completed"
	MicroQuizJobStatusFailed     = "failed"
)

// Micro quiz statuses
const (
	MicroQuizStatusDraft     = "draft"
	MicroQuizStatusPublished = "published"
	MicroQuizStatusArchived  = "archived"
)

// MicroQuizJob represents a quiz generation job - one job produces many quizzes (one per node).
type MicroQuizJob struct {
	ID              int64          `json:"id" db:"id"`
	CourseID        int64          `json:"course_id" db:"course_id"`
	SectionID       sql.NullInt64  `json:"section_id" db:"section_id"`
	SourceContentID sql.NullInt64  `json:"source_content_id" db:"source_content_id"`
	SourceFilePath  sql.NullString `json:"source_file_path" db:"source_file_path"`
	SourceFileType  sql.NullString `json:"source_file_type" db:"source_file_type"`
	SourceURL       sql.NullString `json:"source_url" db:"source_url"`
	Language        string         `json:"language" db:"language"`
	Status          string         `json:"status" db:"status"`
	Progress        int            `json:"progress" db:"progress"`
	Stage           string         `json:"stage" db:"stage"`
	QuizzesCount    int            `json:"quizzes_count" db:"quizzes_count"`
	Error           sql.NullString `json:"error" db:"error"`
	CreatedBy       int64          `json:"created_by" db:"created_by"`
	CreatedAt       time.Time      `json:"created_at" db:"created_at"`
	UpdatedAt       time.Time      `json:"updated_at" db:"updated_at"`
	CompletedAt     sql.NullTime   `json:"completed_at" db:"completed_at"`
}

// MicroQuiz represents a single AI-generated quiz covering one knowledge node.
// questions_json is the single source of truth for quiz content (structured JSON array).
type MicroQuiz struct {
	ID                 int64          `json:"id" db:"id"`
	JobID              int64          `json:"job_id" db:"job_id"`
	CourseID           int64          `json:"course_id" db:"course_id"`
	SectionID          sql.NullInt64  `json:"section_id" db:"section_id"`
	SourceContentID    sql.NullInt64  `json:"source_content_id" db:"source_content_id"`
	Title              string         `json:"title" db:"title"`
	Summary            sql.NullString `json:"summary" db:"summary"`
	QuestionsJSON      json.RawMessage `json:"questions_json" db:"questions_json"`
	QuestionsCount     int            `json:"questions_count" db:"questions_count"`
	OrderIndex         int            `json:"order_index" db:"order_index"`
	Status             string         `json:"status" db:"status"`
	PublishedContentID sql.NullInt64  `json:"published_content_id" db:"published_content_id"`
	NodeID             sql.NullInt64  `json:"node_id" db:"node_id"`
	Language           string         `json:"language" db:"language"`
	CreatedBy          int64          `json:"created_by" db:"created_by"`
	CreatedAt          time.Time      `json:"created_at" db:"created_at"`
	UpdatedAt          time.Time      `json:"updated_at" db:"updated_at"`
	PublishedAt        sql.NullTime   `json:"published_at" db:"published_at"`
}
