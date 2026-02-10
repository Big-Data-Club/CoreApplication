package dto

import (
	"database/sql"
	"time"

	"example/hello/internal/models"
)

// QuizAttemptDTO represents a quiz attempt for API responses
type QuizAttemptDTO struct {
	ID                 int64     `json:"id"`
	QuizID             int64     `json:"quiz_id"`
	StudentID          int64     `json:"student_id"`
	AttemptNumber      int       `json:"attempt_number"`
	StartedAt          time.Time `json:"started_at"`
	SubmittedAt        *time.Time `json:"submitted_at"`
	TimeSpentSeconds   *int      `json:"time_spent_seconds"`
	TotalPoints        *float64  `json:"total_points"`
	EarnedPoints       *float64  `json:"earned_points"`
	Percentage         *float64  `json:"percentage"`
	IsPassed           *bool     `json:"is_passed"`
	Status             string    `json:"status"`
	AutoGradedAt       *time.Time `json:"auto_graded_at"`
	ManuallyGradedAt   *time.Time `json:"manually_graded_at"`
	GradedBy           *int64    `json:"graded_by"`
	IPAddress          *string   `json:"ip_address"`
	UserAgent          *string   `json:"user_agent"`
	CreatedAt          time.Time `json:"created_at"`
	UpdatedAt          time.Time `json:"updated_at"`
	QuizTitle          string    `json:"quiz_title"`
	QuizTotalPoints    float64   `json:"quiz_total_points"`
	PassingScore       *float64  `json:"passing_score"`
	StudentName        string    `json:"student_name"`
	StudentEmail       string    `json:"student_email"`
	AnsweredQuestions  int       `json:"answered_questions"`
	CorrectAnswers     int       `json:"correct_answers"`
}

// ToQuizAttemptDTO converts QuizAttemptWithDetails to DTO
func ToQuizAttemptDTO(attempt models.QuizAttemptWithDetails) QuizAttemptDTO {
	dto := QuizAttemptDTO{
		ID:                attempt.ID,
		QuizID:            attempt.QuizID,
		StudentID:         attempt.StudentID,
		AttemptNumber:     attempt.AttemptNumber,
		StartedAt:         attempt.StartedAt,
		Status:            attempt.Status,
		CreatedAt:         attempt.CreatedAt,
		UpdatedAt:         attempt.UpdatedAt,
		QuizTitle:         attempt.QuizTitle,
		QuizTotalPoints:   attempt.QuizTotalPoints,
		StudentName:       attempt.StudentName,
		StudentEmail:      attempt.StudentEmail,
		AnsweredQuestions: attempt.AnsweredQuestions,
		CorrectAnswers:    attempt.CorrectAnswers,
	}

	// Handle nullable fields
	if attempt.SubmittedAt.Valid {
		dto.SubmittedAt = &attempt.SubmittedAt.Time
	}

	if attempt.TimeSpentSeconds.Valid {
		seconds := int(attempt.TimeSpentSeconds.Int32)
		dto.TimeSpentSeconds = &seconds
	}

	if attempt.TotalPoints.Valid {
		dto.TotalPoints = &attempt.TotalPoints.Float64
	}

	if attempt.EarnedPoints.Valid {
		dto.EarnedPoints = &attempt.EarnedPoints.Float64
	}

	if attempt.Percentage.Valid {
		dto.Percentage = &attempt.Percentage.Float64
	}

	if attempt.IsPassed.Valid {
		dto.IsPassed = &attempt.IsPassed.Bool
	}

	if attempt.AutoGradedAt.Valid {
		dto.AutoGradedAt = &attempt.AutoGradedAt.Time
	}

	if attempt.ManuallyGradedAt.Valid {
		dto.ManuallyGradedAt = &attempt.ManuallyGradedAt.Time
	}

	if attempt.GradedBy.Valid {
		dto.GradedBy = &attempt.GradedBy.Int64
	}

	if attempt.IPAddress.Valid {
		dto.IPAddress = &attempt.IPAddress.String
	}

	if attempt.UserAgent.Valid {
		dto.UserAgent = &attempt.UserAgent.String
	}

	if attempt.PassingScore.Valid {
		dto.PassingScore = &attempt.PassingScore.Float64
	}

	return dto
}

// ToQuizAttemptDTOList converts a list of QuizAttemptWithDetails to DTOs
func ToQuizAttemptDTOList(attempts []models.QuizAttemptWithDetails) []QuizAttemptDTO {
	dtos := make([]QuizAttemptDTO, len(attempts))
	for i, attempt := range attempts {
		dtos[i] = ToQuizAttemptDTO(attempt)
	}
	return dtos
}

// QuizAttemptSummaryDTO represents the summary response
type QuizAttemptSummaryDTO struct {
	Attempt           QuizAttemptDTO      `json:"attempt"`
	QuestionBreakdown []QuestionResultDTO `json:"question_breakdown"`
	TimeBreakdown     TimeBreakdownDTO    `json:"time_breakdown"`
	ScoreBreakdown    ScoreBreakdownDTO   `json:"score_breakdown"`
}

type QuestionResultDTO struct {
	QuestionID       int64   `json:"question_id"`
	QuestionText     string  `json:"question_text"`
	QuestionType     string  `json:"question_type"`
	Points           float64 `json:"points"`
	PointsEarned     float64 `json:"points_earned"`
	IsCorrect        bool    `json:"is_correct"`
	TimeSpentSeconds int     `json:"time_spent_seconds"`
	AnsweredAt       string  `json:"answered_at"`
}

type TimeBreakdownDTO struct {
	TotalSeconds       int    `json:"total_seconds"`
	TotalMinutes       int    `json:"total_minutes"`
	AveragePerQuestion int    `json:"average_per_question"`
	FormattedDuration  string `json:"formatted_duration"`
}

type ScoreBreakdownDTO struct {
	TotalPoints    float64 `json:"total_points"`
	EarnedPoints   float64 `json:"earned_points"`
	Percentage     float64 `json:"percentage"`
	PassingScore   float64 `json:"passing_score"`
	IsPassed       bool    `json:"is_passed"`
	CorrectCount   int     `json:"correct_count"`
	IncorrectCount int     `json:"incorrect_count"`
	UngradedCount  int     `json:"ungraded_count"`
}

// Helper to convert NullTime to pointer
func NullTimeToPtr(nt sql.NullTime) *time.Time {
	if nt.Valid {
		return &nt.Time
	}
	return nil
}

// Helper to convert NullInt32 to pointer
func NullInt32ToPtr(ni sql.NullInt32) *int {
	if ni.Valid {
		val := int(ni.Int32)
		return &val
	}
	return nil
}

// Helper to convert NullFloat64 to pointer
func NullFloat64ToPtr(nf sql.NullFloat64) *float64 {
	if nf.Valid {
		return &nf.Float64
	}
	return nil
}

// Helper to convert NullBool to pointer
func NullBoolToPtr(nb sql.NullBool) *bool {
	if nb.Valid {
		return &nb.Bool
	}
	return nil
}

// Helper to convert NullString to pointer
func NullStringToPtr(ns sql.NullString) *string {
	if ns.Valid {
		return &ns.String
	}
	return nil
}

// Helper to convert NullInt64 to pointer
func NullInt64ToPtr(ni sql.NullInt64) *int64 {
	if ni.Valid {
		return &ni.Int64
	}
	return nil
}