package service

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"example/hello/internal/models"
)

// GetStudentAttempts retrieves all attempts by a student for a specific quiz
func (s *QuizService) GetStudentAttempts(ctx context.Context, quizID, studentID int64) ([]models.QuizAttemptWithDetails, error) {
	// Verify quiz exists
	quiz, err := s.quizRepo.GetQuiz(ctx, quizID)
	if err != nil {
		return nil, errors.New("quiz not found")
	}

	if _, err := s.authorizeQuizRead(ctx, quiz, studentID, "STUDENT"); err != nil {
		return nil, err
	}
	// Get all attempts by this student for this quiz
	attempts, err := s.quizRepo.GetStudentAttempts(ctx, quizID, studentID)
	if err != nil {
		return nil, err
	}

	for i := range attempts {
		if !quiz.ShowResultsImmediately || attempts[i].Status == models.AttemptStatusInProgress {
			attempts[i].EarnedPoints = sql.NullFloat64{}
			attempts[i].Percentage = sql.NullFloat64{}
			attempts[i].IsPassed = sql.NullBool{}
			attempts[i].CorrectAnswers = 0
		}
	}

	return attempts, nil
}

// AttemptSummary represents a detailed summary of a quiz attempt
type AttemptSummary struct {
	Attempt           models.QuizAttemptWithDetails `json:"attempt"`
	QuestionBreakdown []QuestionResult              `json:"question_breakdown"`
	TimeBreakdown     TimeBreakdown                 `json:"time_breakdown"`
	ScoreBreakdown    ScoreBreakdown                `json:"score_breakdown"`
	GradingStatus     GradingStatus                 `json:"grading_status"`
}

type GradingStatus struct {
	IsFullyGraded       bool `json:"is_fully_graded"`
	PendingGradingCount int  `json:"pending_grading_count"`
	IsProvisional       bool `json:"is_provisional"`
}

type QuestionResult struct {
	QuestionID       int64   `json:"question_id"`
	QuestionText     string  `json:"question_text"`
	QuestionType     string  `json:"question_type"`
	Points           float64 `json:"points"`
	PointsEarned     float64 `json:"points_earned"`
	IsCorrect        bool    `json:"is_correct"`
	TimeSpentSeconds int     `json:"time_spent_seconds"`
	AnsweredAt       string  `json:"answered_at"`
}

type TimeBreakdown struct {
	TotalSeconds       int    `json:"total_seconds"`
	TotalMinutes       int    `json:"total_minutes"`
	AveragePerQuestion int    `json:"average_per_question"`
	FormattedDuration  string `json:"formatted_duration"`
}

type ScoreBreakdown struct {
	TotalPoints    float64 `json:"total_points"`
	EarnedPoints   float64 `json:"earned_points"`
	Percentage     float64 `json:"percentage"`
	PassingScore   float64 `json:"passing_score"`
	IsPassed       bool    `json:"is_passed"`
	CorrectCount   int     `json:"correct_count"`
	IncorrectCount int     `json:"incorrect_count"`
	UngradedCount  int     `json:"ungraded_count"`
}

// GetAttemptSummary retrieves detailed summary of an attempt
func (s *QuizService) GetAttemptSummary(ctx context.Context, attemptID, userID int64) (*AttemptSummary, error) {
	// Get attempt with details
	attempt, err := s.quizRepo.GetAttemptWithDetails(ctx, attemptID)
	if err != nil || attempt == nil {
		return nil, errors.New("attempt not found")
	}

	if attempt.StudentID == userID {
		quiz, err := s.quizRepo.GetQuiz(ctx, attempt.QuizID)
		if err != nil {
			return nil, err
		}
		if attempt.Status == models.AttemptStatusInProgress || !quiz.ShowResultsImmediately {
			return nil, fmt.Errorf("results not available")
		}
	}
	if attempt.StudentID != userID {
		roles, err := s.userRepo.GetUserRoles(ctx, userID)
		if err != nil {
			return nil, err
		}
		role := ""
		for _, value := range roles {
			if value == "ADMIN" {
				role = value
				break
			}
		}
		if err := s.verifyQuizOwnership(ctx, attempt.QuizID, userID, role); err != nil {
			return nil, err
		}
	}

	// Get all answers for this attempt
	answers, err := s.quizRepo.GetAttemptAnswers(ctx, attemptID)
	if err != nil {
		return nil, err
	}

	// Get all questions for the quiz
	questions, err := s.quizRepo.ListQuestions(ctx, attempt.QuizID)
	if err != nil {
		return nil, err
	}

	// Build question breakdown
	questionBreakdown := make([]QuestionResult, 0)
	correctCount := 0
	incorrectCount := 0
	ungradedCount := 0
	pendingGradingCount := 0

	for _, q := range questions {
		result := QuestionResult{
			QuestionID:   q.ID,
			QuestionText: q.QuestionText,
			QuestionType: q.QuestionType,
			Points:       q.Points,
		}

		// Find answer for this question
		answerFound := false
		for _, ans := range answers {
			if ans.QuestionID == q.ID {
				answerFound = true
				if ans.PointsEarned.Valid {
					result.PointsEarned = ans.PointsEarned.Float64
				}
				if ans.IsCorrect.Valid {
					result.IsCorrect = ans.IsCorrect.Bool
					if ans.IsCorrect.Bool {
						correctCount++
					} else {
						incorrectCount++
					}
				} else {
					ungradedCount++
					// Check if this is a question type that requires manual grading
					if q.QuestionType == models.QuestionTypeEssay ||
						q.QuestionType == models.QuestionTypeFileUpload ||
						q.QuestionType == models.QuestionTypeShortAnswer {
						// Only count as pending if answer exists but not graded
						if !ans.PointsEarned.Valid {
							pendingGradingCount++
						}
					}
				}
				if ans.TimeSpentSeconds.Valid {
					result.TimeSpentSeconds = int(ans.TimeSpentSeconds.Int32)
				}
				result.AnsweredAt = ans.AnsweredAt.Format(time.RFC3339)
				break
			}
		}

		// If no answer found for required manual grading question, count as pending
		if !answerFound && (q.QuestionType == models.QuestionTypeEssay ||
			q.QuestionType == models.QuestionTypeFileUpload ||
			q.QuestionType == models.QuestionTypeShortAnswer) {
			pendingGradingCount++
		}

		questionBreakdown = append(questionBreakdown, result)
	}

	// Calculate time breakdown
	totalSeconds := 0
	if attempt.TimeSpentSeconds.Valid {
		totalSeconds = int(attempt.TimeSpentSeconds.Int32)
	}
	avgPerQuestion := 0
	if len(questions) > 0 {
		avgPerQuestion = totalSeconds / len(questions)
	}

	timeBreakdown := TimeBreakdown{
		TotalSeconds:       totalSeconds,
		TotalMinutes:       totalSeconds / 60,
		AveragePerQuestion: avgPerQuestion,
		FormattedDuration:  formatDuration(totalSeconds),
	}

	// Calculate score breakdown
	totalPoints := attempt.QuizTotalPoints
	earnedPoints := 0.0
	if attempt.EarnedPoints.Valid {
		earnedPoints = attempt.EarnedPoints.Float64
	}
	percentage := 0.0
	if attempt.Percentage.Valid {
		percentage = attempt.Percentage.Float64
	}
	passingScore := 0.0
	if attempt.PassingScore.Valid {
		passingScore = attempt.PassingScore.Float64
	}
	isPassed := false
	if attempt.IsPassed.Valid {
		isPassed = attempt.IsPassed.Bool
	}

	scoreBreakdown := ScoreBreakdown{
		TotalPoints:    totalPoints,
		EarnedPoints:   earnedPoints,
		Percentage:     percentage,
		PassingScore:   passingScore,
		IsPassed:       isPassed,
		CorrectCount:   correctCount,
		IncorrectCount: incorrectCount,
		UngradedCount:  ungradedCount,
	}

	// Calculate grading status
	isFullyGraded := pendingGradingCount == 0
	gradingStatus := GradingStatus{
		IsFullyGraded:       isFullyGraded,
		PendingGradingCount: pendingGradingCount,
		IsProvisional:       !isFullyGraded, // Điểm tạm thời nếu chưa chấm hết
	}

	return &AttemptSummary{
		Attempt:           *attempt,
		QuestionBreakdown: questionBreakdown,
		TimeBreakdown:     timeBreakdown,
		ScoreBreakdown:    scoreBreakdown,
		GradingStatus:     gradingStatus,
	}, nil
}

func formatDuration(seconds int) string {
	hours := seconds / 3600
	minutes := (seconds % 3600) / 60
	secs := seconds % 60

	if hours > 0 {
		return fmt.Sprintf("%dh %dm %ds", hours, minutes, secs)
	} else if minutes > 0 {
		return fmt.Sprintf("%dm %ds", minutes, secs)
	}
	return fmt.Sprintf("%ds", secs)
}

// GetAttempt retrieves a single quiz attempt
func (s *QuizService) GetAttempt(ctx context.Context, attemptID int64) (*models.QuizAttempt, error) {
	attempt, err := s.quizRepo.GetAttempt(ctx, attemptID)
	if err != nil {
		return nil, errors.New("attempt not found")
	}
	return attempt, nil
}

// GetAttemptAnswers retrieves all answers for a quiz attempt
func (s *QuizService) GetAttemptAnswers(ctx context.Context, attemptID, userID int64) ([]models.QuizStudentAnswer, error) {
	attempt, err := s.quizRepo.GetAttempt(ctx, attemptID)
	if err != nil {
		return nil, err
	}
	if attempt == nil {
		return nil, sql.ErrNoRows
	}

	if attempt.StudentID != userID {
		return nil, ErrQuizAccess
	}
	quiz, err := s.quizRepo.GetQuiz(ctx, attempt.QuizID)
	if err != nil {
		return nil, err
	}
	answers, err := s.quizRepo.GetAttemptAnswers(ctx, attemptID)
	if err != nil {
		return nil, err
	}
	if attempt.Status == models.AttemptStatusInProgress || !quiz.ShowResultsImmediately {
		for i := range answers {
			answers[i].IsCorrect = sql.NullBool{}
			answers[i].PointsEarned = sql.NullFloat64{}
			answers[i].GraderFeedback = sql.NullString{}
			answers[i].GradedBy = sql.NullInt64{}
			answers[i].GradedAt = sql.NullTime{}
		}
	}
	return answers, nil
}
