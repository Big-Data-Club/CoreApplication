package models

import (
	"database/sql"
	"time"
)

// ============================================
// QUIZ MODELS
// ============================================

// Quiz represents a quiz configuration
type Quiz struct {
	ID                   int64          `json:"id" db:"id"`
	ContentID            int64          `json:"content_id" db:"content_id"`
	Title                string         `json:"title" db:"title"`
	Description          sql.NullString `json:"description" db:"description"`
	Instructions         sql.NullString `json:"instructions" db:"instructions"`
	TimeLimitMinutes     sql.NullInt32  `json:"time_limit_minutes" db:"time_limit_minutes"`
	AvailableFrom        sql.NullTime   `json:"available_from" db:"available_from"`
	AvailableUntil       sql.NullTime   `json:"available_until" db:"available_until"`
	MaxAttempts          sql.NullInt32  `json:"max_attempts" db:"max_attempts"`
	ShuffleQuestions     bool           `json:"shuffle_questions" db:"shuffle_questions"`
	ShuffleAnswers       bool           `json:"shuffle_answers" db:"shuffle_answers"`
	PassingScore         sql.NullFloat64 `json:"passing_score" db:"passing_score"`
	TotalPoints          float64        `json:"total_points" db:"total_points"`
	AutoGrade            bool           `json:"auto_grade" db:"auto_grade"`
	ShowResultsImmediately bool         `json:"show_results_immediately" db:"show_results_immediately"`
	ShowCorrectAnswers   bool           `json:"show_correct_answers" db:"show_correct_answers"`
	AllowReview          bool           `json:"allow_review" db:"allow_review"`
	ShowFeedback         bool           `json:"show_feedback" db:"show_feedback"`
	IsPublished          bool           `json:"is_published" db:"is_published"`
	CreatedBy            int64          `json:"created_by" db:"created_by"`
	CreatedAt            time.Time      `json:"created_at" db:"created_at"`
	UpdatedAt            time.Time      `json:"updated_at" db:"updated_at"`
}

// QuizWithStats includes quiz statistics
type QuizWithStats struct {
	Quiz
	CreatorName   string         `json:"creator_name" db:"creator_name"`
	CreatorEmail  string         `json:"creator_email" db:"creator_email"`
	QuestionCount int            `json:"question_count" db:"question_count"`
	AttemptCount  int            `json:"attempt_count" db:"attempt_count"`
	StudentCount  int            `json:"student_count" db:"student_count"`
	AverageScore  sql.NullFloat64 `json:"average_score" db:"average_score"`
	PassedCount   int            `json:"passed_count" db:"passed_count"`
}

// ============================================
// QUESTION MODELS
// ============================================

// QuizQuestion represents a question in a quiz
type QuizQuestion struct {
	ID           int64          `json:"id" db:"id"`
	QuizID       int64          `json:"quiz_id" db:"quiz_id"`
	QuestionType string         `json:"question_type" db:"question_type"`
	QuestionText string         `json:"question_text" db:"question_text"`
	QuestionHTML sql.NullString `json:"question_html" db:"question_html"`
	Explanation  sql.NullString `json:"explanation" db:"explanation"`
	Points       float64        `json:"points" db:"points"`
	OrderIndex   int            `json:"order_index" db:"order_index"`
	Settings     []byte         `json:"settings" db:"settings"` // JSONB
	IsRequired   bool           `json:"is_required" db:"is_required"`
	CreatedAt    time.Time      `json:"created_at" db:"created_at"`
	UpdatedAt    time.Time      `json:"updated_at" db:"updated_at"`
}

// QuestionWithOptions includes answer options
type QuestionWithOptions struct {
	QuizQuestion
	AnswerOptions  []QuizAnswerOption  `json:"answer_options"`
	CorrectAnswers []QuizCorrectAnswer `json:"correct_answers"`
}

// ============================================
// ANSWER OPTION MODELS
// ============================================

// QuizAnswerOption represents an answer option for choice questions
type QuizAnswerOption struct {
	ID          int64          `json:"id" db:"id"`
	QuestionID  int64          `json:"question_id" db:"question_id"`
	OptionText  string         `json:"option_text" db:"option_text"`
	OptionHTML  sql.NullString `json:"option_html" db:"option_html"`
	IsCorrect   bool           `json:"is_correct" db:"is_correct"`
	OrderIndex  int            `json:"order_index" db:"order_index"`
	BlankID     sql.NullInt32  `json:"blank_id" db:"blank_id"`
	CreatedAt   time.Time      `json:"created_at" db:"created_at"`
	Settings    []byte         `json:"settings"`
}

// ============================================
// CORRECT ANSWER MODELS
// ============================================

// QuizCorrectAnswer represents correct answer for text-based questions
type QuizCorrectAnswer struct {
	ID            int64          `json:"id" db:"id"`
	QuestionID    int64          `json:"question_id" db:"question_id"`
	AnswerText    sql.NullString `json:"answer_text" db:"answer_text"`
	BlankID       sql.NullInt32  `json:"blank_id" db:"blank_id"`
	BlankPosition sql.NullInt32  `json:"blank_position" db:"blank_position"`
	CaseSensitive bool           `json:"case_sensitive" db:"case_sensitive"`
	ExactMatch    bool           `json:"exact_match" db:"exact_match"`
	CreatedAt     time.Time      `json:"created_at" db:"created_at"`
}

// ============================================
// ATTEMPT MODELS
// ============================================

// QuizAttempt represents a student's attempt at a quiz
type QuizAttempt struct {
	ID               int64          `json:"id" db:"id"`
	QuizID           int64          `json:"quiz_id" db:"quiz_id"`
	StudentID        int64          `json:"student_id" db:"student_id"`
	AttemptNumber    int            `json:"attempt_number" db:"attempt_number"`
	StartedAt        time.Time      `json:"started_at" db:"started_at"`
	SubmittedAt      sql.NullTime   `json:"submitted_at" db:"submitted_at"`
	TimeSpentSeconds sql.NullInt32  `json:"time_spent_seconds" db:"time_spent_seconds"`
	TotalPoints      sql.NullFloat64 `json:"total_points" db:"total_points"`
	EarnedPoints     sql.NullFloat64 `json:"earned_points" db:"earned_points"`
	Percentage       sql.NullFloat64 `json:"percentage" db:"percentage"`
	IsPassed         sql.NullBool   `json:"is_passed" db:"is_passed"`
	Status           string         `json:"status" db:"status"`
	AutoGradedAt     sql.NullTime   `json:"auto_graded_at" db:"auto_graded_at"`
	ManuallyGradedAt sql.NullTime   `json:"manually_graded_at" db:"manually_graded_at"`
	GradedBy         sql.NullInt64  `json:"graded_by" db:"graded_by"`
	IPAddress        sql.NullString `json:"ip_address" db:"ip_address"`
	UserAgent        sql.NullString `json:"user_agent" db:"user_agent"`
	CreatedAt        time.Time      `json:"created_at" db:"created_at"`
	UpdatedAt        time.Time      `json:"updated_at" db:"updated_at"`
}

// QuizAttemptWithDetails includes quiz and student details
type QuizAttemptWithDetails struct {
	QuizAttempt
	QuizTitle        string         `json:"quiz_title" db:"quiz_title"`
	QuizTotalPoints  float64        `json:"quiz_total_points" db:"quiz_total_points"`
	PassingScore     sql.NullFloat64 `json:"passing_score" db:"passing_score"`
	StudentName      string         `json:"student_name" db:"student_name"`
	StudentEmail     string         `json:"student_email" db:"student_email"`
	AnsweredQuestions int           `json:"answered_questions" db:"answered_questions"`
	CorrectAnswers   int            `json:"correct_answers" db:"correct_answers"`
}

// ============================================
// STUDENT ANSWER MODELS
// ============================================

// QuizStudentAnswer represents a student's answer to a question
type QuizStudentAnswer struct {
	ID               int64          `json:"id" db:"id"`
	AttemptID        int64          `json:"attempt_id" db:"attempt_id"`
	QuestionID       int64          `json:"question_id" db:"question_id"`
	AnswerData       []byte         `json:"answer_data" db:"answer_data"` // JSONB
	PointsEarned     sql.NullFloat64 `json:"points_earned" db:"points_earned"`
	IsCorrect        sql.NullBool   `json:"is_correct" db:"is_correct"`
	GraderFeedback   sql.NullString `json:"grader_feedback" db:"grader_feedback"`
	GradedBy         sql.NullInt64  `json:"graded_by" db:"graded_by"`
	GradedAt         sql.NullTime   `json:"graded_at" db:"graded_at"`
	AnsweredAt       time.Time      `json:"answered_at" db:"answered_at"`
	TimeSpentSeconds sql.NullInt32  `json:"time_spent_seconds" db:"time_spent_seconds"`
	CreatedAt        time.Time      `json:"created_at" db:"created_at"`
	UpdatedAt        time.Time      `json:"updated_at" db:"updated_at"`
}

// ============================================
// ANALYTICS MODELS
// ============================================

// QuizAnalytics represents analytics for a quiz or question
type QuizAnalytics struct {
	ID               int64          `json:"id" db:"id"`
	QuizID           int64          `json:"quiz_id" db:"quiz_id"`
	QuestionID       sql.NullInt64  `json:"question_id" db:"question_id"`
	TotalAttempts    int            `json:"total_attempts" db:"total_attempts"`
	CorrectCount     int            `json:"correct_count" db:"correct_count"`
	IncorrectCount   int            `json:"incorrect_count" db:"incorrect_count"`
	AverageScore     sql.NullFloat64 `json:"average_score" db:"average_score"`
	DifficultyRating sql.NullString `json:"difficulty_rating" db:"difficulty_rating"`
	UpdatedAt        time.Time      `json:"updated_at" db:"updated_at"`
}

// ============================================
// CONSTANTS
// ============================================

// Question types
const (
	QuestionTypeSingleChoice      = "SINGLE_CHOICE"
	QuestionTypeMultipleChoice    = "MULTIPLE_CHOICE"
	QuestionTypeShortAnswer       = "SHORT_ANSWER"
	QuestionTypeEssay             = "ESSAY"
	QuestionTypeFileUpload        = "FILE_UPLOAD"
	QuestionTypeFillBlankText     = "FILL_BLANK_TEXT"
	QuestionTypeFillBlankDropdown = "FILL_BLANK_DROPDOWN"
)

// Attempt status
const (
	AttemptStatusInProgress = "IN_PROGRESS"
	AttemptStatusSubmitted  = "SUBMITTED"
	AttemptStatusGraded     = "GRADED"
	AttemptStatusAbandoned  = "ABANDONED"
)

// Difficulty ratings
const (
	DifficultyEasy   = "EASY"
	DifficultyMedium = "MEDIUM"
	DifficultyHard   = "HARD"
)