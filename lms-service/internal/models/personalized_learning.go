package models

import (
	"database/sql"
	"time"
)

// ══════════════════════════════════════════════════════════════════════════════
// SKILL MODELS
// ══════════════════════════════════════════════════════════════════════════════

// Skill represents a learning skill in the taxonomy
type Skill struct {
	ID            int64           `json:"id" db:"id"`
	Name          string          `json:"name" db:"name"`
	Description   sql.NullString  `json:"description" db:"description"`
	ParentSkillID sql.NullInt64   `json:"parent_skill_id" db:"parent_skill_id"`
	Difficulty    sql.NullFloat64 `json:"difficulty" db:"difficulty"`
	CreatedAt     time.Time       `json:"created_at" db:"created_at"`
	UpdatedAt     time.Time       `json:"updated_at" db:"updated_at"`
}

// SkillWithChildren includes child skills for hierarchy display
type SkillWithChildren struct {
	Skill
	Children []Skill `json:"children,omitempty"`
}

// SkillPrerequisite represents skill dependencies
type SkillPrerequisite struct {
	ID                  int64     `json:"id" db:"id"`
	SkillID             int64     `json:"skill_id" db:"skill_id"`
	PrerequisiteSkillID int64     `json:"prerequisite_skill_id" db:"prerequisite_skill_id"`
	Strength            float64   `json:"strength" db:"strength"`
	CreatedAt           time.Time `json:"created_at" db:"created_at"`
}

// SkillWithPrerequisites includes prerequisite skill information
type SkillWithPrerequisites struct {
	Skill
	Prerequisites []SkillPrerequisite `json:"prerequisites"`
}

// ContentSkill maps content to skills
type ContentSkill struct {
	ID         int64           `json:"id" db:"id"`
	ContentID  int64           `json:"content_id" db:"content_id"`
	SkillID    int64           `json:"skill_id" db:"skill_id"`
	Difficulty sql.NullFloat64 `json:"difficulty" db:"difficulty"`
	Weight     float64         `json:"weight" db:"weight"`
	CreatedAt  time.Time       `json:"created_at" db:"created_at"`
}

// QuestionSkill maps quiz questions to skills
type QuestionSkill struct {
	ID         int64           `json:"id" db:"id"`
	QuestionID int64           `json:"question_id" db:"question_id"`
	SkillID    int64           `json:"skill_id" db:"skill_id"`
	Difficulty sql.NullFloat64 `json:"difficulty" db:"difficulty"`
	Weight     float64         `json:"weight" db:"weight"`
	CreatedAt  time.Time       `json:"created_at" db:"created_at"`
}

// ══════════════════════════════════════════════════════════════════════════════
// LEARNING EVENT MODELS
// ══════════════════════════════════════════════════════════════════════════════

// LearningEvent tracks all learning interactions (immutable)
type LearningEvent struct {
	ID             int64           `json:"id" db:"id"`
	EventID        string          `json:"event_id" db:"event_id"`
	EventType      string          `json:"event_type" db:"event_type"`
	StudentID      int64           `json:"student_id" db:"student_id"`
	SessionID      sql.NullString  `json:"session_id" db:"session_id"`
	CourseID       sql.NullInt64   `json:"course_id" db:"course_id"`
	LessonID       sql.NullInt64   `json:"lesson_id" db:"lesson_id"`
	QuestionID     sql.NullInt64   `json:"question_id" db:"question_id"`
	SkillID        sql.NullInt64   `json:"skill_id" db:"skill_id"`
	Difficulty     sql.NullFloat64 `json:"difficulty" db:"difficulty"`
	Correct        sql.NullBool    `json:"correct" db:"correct"`
	AttemptNo      sql.NullInt32   `json:"attempt_no" db:"attempt_no"`
	ResponseTimeMs sql.NullInt64   `json:"response_time_ms" db:"response_time_ms"`
	HintCount      sql.NullInt32   `json:"hint_count" db:"hint_count"`
	Metadata       []byte          `json:"metadata" db:"metadata"`
	CreatedAt      time.Time       `json:"created_at" db:"created_at"`
}

// LearningEventWithDetails includes related entity information
type LearningEventWithDetails struct {
	LearningEvent
	StudentName string         `json:"student_name,omitempty" db:"student_name"`
	CourseName  sql.NullString `json:"course_name,omitempty" db:"course_name"`
	SkillName   sql.NullString `json:"skill_name,omitempty" db:"skill_name"`
}

// ══════════════════════════════════════════════════════════════════════════════
// LEARNER SKILL STATE MODELS
// ══════════════════════════════════════════════════════════════════════════════

// LearnerSkillState represents mastery state for a student+skill pair
type LearnerSkillState struct {
	ID                    int64           `json:"id" db:"id"`
	StudentID             int64           `json:"student_id" db:"student_id"`
	SkillID               int64           `json:"skill_id" db:"skill_id"`
	MasteryScore          float64         `json:"mastery_score" db:"mastery_score"`
	ConfidenceScore       float64         `json:"confidence_score" db:"confidence_score"`
	AttemptCount          int             `json:"attempt_count" db:"attempt_count"`
	Accuracy              float64         `json:"accuracy" db:"accuracy"`
	AvgResponseTimeMs     sql.NullInt64   `json:"avg_response_time_ms" db:"avg_response_time_ms"`
	HintDependency        float64         `json:"hint_dependency" db:"hint_dependency"`
	LastPracticedAt       sql.NullTime    `json:"last_practiced_at" db:"last_practiced_at"`
	RecommendedDifficulty sql.NullFloat64 `json:"recommended_difficulty" db:"recommended_difficulty"`
	UpdatedAt             time.Time       `json:"updated_at" db:"updated_at"`
}

// LearnerSkillStateWithSkill includes skill information
type LearnerSkillStateWithSkill struct {
	LearnerSkillState
	SkillName        string          `json:"skill_name" db:"skill_name"`
	SkillDescription sql.NullString  `json:"skill_description" db:"skill_description"`
	SkillDifficulty  sql.NullFloat64 `json:"skill_difficulty" db:"skill_difficulty"`
}

// PersonalizedContent is a published LMS item mapped to a skill. It is the
// minimum data needed to make a recommendation navigable by the client.
type PersonalizedContent struct {
	ContentID    int64   `json:"content_id" db:"content_id"`
	ContentTitle string  `json:"content_title" db:"content_title"`
	ContentType  string  `json:"content_type" db:"content_type"`
	CourseTitle  string  `json:"course_title" db:"course_title"`
	Difficulty   float64 `json:"difficulty" db:"difficulty"`
}

// SkillContentCandidate is one navigable content item mapped to a skill,
// consumed by the recommender-service next-best-lesson engine.
type SkillContentCandidate struct {
	ContentID   int64   `json:"content_id" db:"content_id"`
	ContentTitle string `json:"content_title" db:"content_title"`
	ContentType string  `json:"content_type" db:"content_type"`
	SkillID     int64   `json:"skill_id" db:"skill_id"`
	SkillName   string  `json:"skill_name" db:"skill_name"`
	Difficulty  float64 `json:"difficulty" db:"difficulty"`
	Completed   bool    `json:"completed" db:"completed"`
}

// CourseSkillProfile is the full skill-based personalization payload for one
// student in one course: current mastery states plus the eligible catalogue.
type CourseSkillProfile struct {
	StudentID       int64                   `json:"student_id"`
	CourseID        int64                   `json:"course_id"`
	SkillStates     []LearnerSkillStateWithSkill `json:"skill_states"`
	AvailableContent []SkillContentCandidate `json:"available_content"`
}

// ══════════════════════════════════════════════════════════════════════════════
// SKILL RECOMMENDATION MODELS
// ══════════════════════════════════════════════════════════════════════════════

// SkillRecommendation tracks recommendations and their outcomes
type SkillRecommendation struct {
	ID                  int64           `json:"id" db:"id"`
	RecommendationID    string          `json:"recommendation_id" db:"recommendation_id"`
	StudentID           int64           `json:"student_id" db:"student_id"`
	CourseID            sql.NullInt64   `json:"course_id" db:"course_id"`
	ContentID           sql.NullInt64   `json:"content_id" db:"content_id"`
	SkillID             sql.NullInt64   `json:"skill_id" db:"skill_id"`
	Difficulty          sql.NullFloat64 `json:"difficulty" db:"difficulty"`
	Reason              sql.NullString  `json:"reason" db:"reason"`
	RecommendationScore sql.NullFloat64 `json:"recommendation_score" db:"recommendation_score"`
	Clicked             bool            `json:"clicked" db:"clicked"`
	ClickedAt           sql.NullTime    `json:"clicked_at" db:"clicked_at"`
	Completed           bool            `json:"completed" db:"completed"`
	CompletedAt         sql.NullTime    `json:"completed_at" db:"completed_at"`
	CreatedAt           time.Time       `json:"created_at" db:"created_at"`
}

// SkillRecommendationWithDetails includes related entity information
type SkillRecommendationWithDetails struct {
	SkillRecommendation
	ContentTitle sql.NullString `json:"content_title,omitempty" db:"content_title"`
	SkillName    sql.NullString `json:"skill_name,omitempty" db:"skill_name"`
	CourseName   sql.NullString `json:"course_name,omitempty" db:"course_name"`
}

// ══════════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ══════════════════════════════════════════════════════════════════════════════

// Learning event types
const (
	EventLessonOpened          = "lesson_opened"
	EventLessonStarted         = "lesson_started"
	EventLessonCompleted       = "lesson_completed"
	EventLessonAbandoned       = "lesson_abandoned"
	EventLessonResumed         = "lesson_resumed"
	EventQuestionViewed        = "question_viewed"
	EventAnswerSubmitted       = "answer_submitted"
	EventAnswerRetried         = "answer_retried"
	EventHintRequested         = "hint_requested"
	EventRecommendationClicked = "recommendation_clicked"
)

// Mastery level thresholds
const (
	MasteryThresholdStruggling = 0.3
	MasteryThresholdDeveloping = 0.6
	MasteryThresholdAdvancing  = 0.8
	MasteryThresholdMastered   = 0.9
)
