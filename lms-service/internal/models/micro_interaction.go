package models

import (
	"database/sql"
	"time"
)

// Micro-lesson interaction action types. Mirrors the CHECK constraint in
// migration V008. Frontend sends these values verbatim.
const (
	MicroActionLessonView         = "lesson_view"
	MicroActionLessonComplete     = "lesson_complete"
	MicroActionFlashcardFlip      = "flashcard_flip"
	MicroActionFlashcardRate      = "flashcard_rate"
	MicroActionQuickCheckAttempt  = "quick_check_attempt"
	MicroActionQuickCheckCorrect  = "quick_check_correct"
	MicroActionQuickCheckIncorrec = "quick_check_incorrect"
	MicroActionAskAI              = "ask_ai"
)

// MicroLessonInteraction is the raw row inserted by the
// POST /analytics/micro-interaction endpoint.
type MicroLessonInteraction struct {
	ID         int64           `json:"id" db:"id"`
	UserID     int64           `json:"user_id" db:"user_id"`
	CourseID   int64           `json:"course_id" db:"course_id"`
	LessonID   sql.NullInt64   `json:"lesson_id" db:"lesson_id"`
	NodeID     sql.NullInt64   `json:"node_id" db:"node_id"`
	ActionType string          `json:"action_type" db:"action_type"`
	Score      sql.NullFloat64 `json:"score" db:"score"`
	Status     sql.NullString  `json:"status" db:"status"`
	Payload    []byte          `json:"payload" db:"payload"`
	CreatedAt  time.Time       `json:"created_at" db:"created_at"`
}

// KnowledgeNodeMastery is the materialised composite mastery score
// maintained by the analytics worker. The heatmap endpoint reads
// directly from this table.
type KnowledgeNodeMastery struct {
	UserID            int64     `json:"user_id" db:"user_id"`
	CourseID          int64     `json:"course_id" db:"course_id"`
	NodeID            int64     `json:"node_id" db:"node_id"`
	FormalQuizScore   float64   `json:"formal_quiz_score" db:"formal_quiz_score"`
	FormalQuizCount   int       `json:"formal_quiz_count" db:"formal_quiz_count"`
	MiniQuizScore     float64   `json:"mini_quiz_score" db:"mini_quiz_score"`
	MiniQuizCount     int       `json:"mini_quiz_count" db:"mini_quiz_count"`
	CompletionScore   float64   `json:"completion_score" db:"completion_score"`
	CompletionCount   int       `json:"completion_count" db:"completion_count"`
	EngagementScore   float64   `json:"engagement_score" db:"engagement_score"`
	EngagementCount   int       `json:"engagement_count" db:"engagement_count"`
	MasteryLevel      float64   `json:"mastery_level" db:"mastery_level"`
	LastInteractionAt time.Time `json:"last_interaction_at" db:"last_interaction_at"`
	UpdatedAt         time.Time `json:"updated_at" db:"updated_at"`
}
