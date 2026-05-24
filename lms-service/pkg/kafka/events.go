package kafka

import "time"

// ProcessDocumentEvent represents the payload sent from LMS to AI Service
type ProcessDocumentEvent struct {
	EventID        string    `json:"event_id"`
	ContentID      int64     `json:"content_id"`
	CourseID       int64     `json:"course_id"`
	CourseName     string    `json:"course_name"`
	InstructorName string    `json:"instructor_name"`
	FileURL        string    `json:"file_url"`
	ContentType    string    `json:"content_type"`
	Title          string    `json:"title"`
	TextContent    string    `json:"text_content,omitempty"`
	CreatedAt      time.Time `json:"created_at"`
}

// ProcessDocumentStatusEvent represents the payload sent from AI back to LMS
type ProcessDocumentStatusEvent struct {
	ContentID     int64  `json:"content_id"`
	JobID         int64  `json:"job_id"`
	Status        string `json:"status"` // "success", "failed"
	ChunksCreated int    `json:"chunks_created"`
	Error         string `json:"error,omitempty"`
}

// AICommandEvent is the generic AI job command format (Quiz, Flashcard, Diagnosis)
type AICommandEvent struct {
	JobID       string      `json:"job_id"`
	CommandType string      `json:"command_type"` // "GENERATE_QUIZ", "GENERATE_FLASHCARD", "DIAGNOSE_ERROR"
	CourseID    int64       `json:"course_id,omitempty"`
	Payload     interface{} `json:"payload"`
	CreatedAt   time.Time   `json:"created_at"`
}

// AIJobStatusEvent represents an update on an AI operation
type AIJobStatusEvent struct {
	JobID    string      `json:"job_id"`
	Status   string      `json:"status"` // "completed", "failed", "processing"
	Result   interface{} `json:"result,omitempty"`
	Error    string      `json:"error,omitempty"`
	Progress int         `json:"progress,omitempty"`
}

// NodeMergedEvent is emitted by the AI service after a "Compact Graph"
// merge so the LMS can rewrite its own `node_id` references.
type NodeMergedEvent struct {
	CourseID    int64   `json:"course_id"`
	SurvivorID  int64   `json:"survivor_id"`
	AbsorbedIDs []int64 `json:"absorbed_ids"`
}

// Topic name for Quick Action Panel micro-interactions.
const TopicMicroInteractions = "lms.analytics.interactions"

// MicroInteractionEvent is published by the LMS service whenever a
// student triggers an interaction in the Quick Action Panel
// (flashcard flip, quick check, ask AI, lesson completion). The
// analytics worker consumes these events and updates
// `knowledge_node_mastery` using the weighted scheme described in
// migration V008.
type MicroInteractionEvent struct {
	InteractionID int64     `json:"interaction_id"`
	UserID        int64     `json:"user_id"`
	CourseID      int64     `json:"course_id"`
	LessonID      *int64    `json:"lesson_id,omitempty"`
	NodeID        *int64    `json:"node_id,omitempty"`
	ActionType    string    `json:"action_type"`
	Score         *float64  `json:"score,omitempty"`
	Status        string    `json:"status,omitempty"`
	CreatedAt     time.Time `json:"created_at"`
}
