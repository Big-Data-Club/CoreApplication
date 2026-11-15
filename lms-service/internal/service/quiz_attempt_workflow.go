package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/models"
)

// StartQuizAttempt starts a new quiz attempt for a student
func (s *QuizService) startQuizAttempt(ctx context.Context, quizID, studentID int64, ipAddress, userAgent string) (*dto.QuizAttemptResponse, error) {
	// Get quiz
	quiz, err := s.quizRepo.GetQuiz(ctx, quizID)
	if err != nil {
		return nil, err
	}

	if _, err := s.authorizeQuizRead(ctx, quiz, studentID, "STUDENT"); err != nil {
		return nil, err
	}
	// Check if quiz is available
	if !quiz.IsPublished {
		return nil, fmt.Errorf("quiz is not published")
	}

	// Check availability window
	now := time.Now()
	if quiz.AvailableFrom.Valid && now.Before(quiz.AvailableFrom.Time) {
		return nil, fmt.Errorf("quiz not available yet")
	}
	if quiz.AvailableUntil.Valid && now.After(quiz.AvailableUntil.Time) {
		return nil, fmt.Errorf("quiz is no longer available")
	}

	// Check for in-progress attempt
	latestAttempt, err := s.quizRepo.GetStudentLatestAttempt(ctx, quizID, studentID)
	if err != nil {
		return nil, err
	}
	if latestAttempt != nil && latestAttempt.Status == models.AttemptStatusInProgress {
		// Return existing attempt
		return s.buildAttemptResponse(latestAttempt), nil
	}

	// Check max attempts
	if quiz.MaxAttempts.Valid {
		count, err := s.quizRepo.GetStudentAttemptCount(ctx, quizID, studentID)
		if err != nil {
			return nil, err
		}
		if count >= int(quiz.MaxAttempts.Int32) {
			return nil, fmt.Errorf("maximum attempts reached")
		}
	}

	// Create new attempt
	attemptNumber := 1
	if latestAttempt != nil {
		attemptNumber = latestAttempt.AttemptNumber + 1
	}

	attempt := &models.QuizAttempt{
		QuizID:        quizID,
		StudentID:     studentID,
		AttemptNumber: attemptNumber,
		Status:        models.AttemptStatusInProgress,
		IPAddress:     toNullString(ipAddress),
		UserAgent:     toNullString(userAgent),
	}

	if err := s.quizRepo.CreateAttempt(ctx, attempt); err != nil {
		return nil, fmt.Errorf("failed to create attempt: %w", err)
	}

	return s.buildAttemptResponse(attempt), nil
}

// SubmitAnswer submits or updates an answer for a question
func (s *QuizService) submitAnswer(ctx context.Context, req *dto.SubmitAnswerRequest, studentID int64) (*dto.StudentAnswerResponse, error) {
	// Verify attempt ownership
	attempt, err := s.quizRepo.GetAttempt(ctx, req.AttemptID)
	if err != nil {
		return nil, err
	}

	if attempt == nil {
		return nil, fmt.Errorf("attempt not found")
	}
	if attempt.StudentID != studentID {
		return nil, ErrQuizAccess
	}

	if attempt.Status != models.AttemptStatusInProgress {
		return nil, fmt.Errorf("attempt is not in progress")
	}

	// Check time limit
	quiz, err := s.quizRepo.GetQuiz(ctx, attempt.QuizID)
	if err != nil {
		return nil, err
	}

	if quiz.TimeLimitMinutes.Valid {
		elapsedSeconds, err := s.quizRepo.GetAttemptElapsedTime(ctx, req.AttemptID)
		if err != nil {
			return nil, fmt.Errorf("failed to get elapsed time: %w", err)
		}
		if float64(elapsedSeconds)/60.0 > float64(quiz.TimeLimitMinutes.Int32) {
			return nil, fmt.Errorf("time limit exceeded")
		}
	}

	// Verify question belongs to quiz
	question, err := s.quizRepo.GetQuestion(ctx, req.QuestionID)
	if err != nil {
		return nil, err
	}

	if question.QuizID != attempt.QuizID {
		return nil, fmt.Errorf("question does not belong to this quiz")
	}

	// Validate answer data format
	if err := s.validateAnswerData(question.QuestionType, req.AnswerData); err != nil {
		return nil, err
	}

	// Marshal answer data
	answerDataJSON, err := json.Marshal(req.AnswerData)
	if err != nil {
		return nil, fmt.Errorf("invalid answer data: %w", err)
	}

	// Check if answer already exists
	existingAnswer, err := s.quizRepo.GetStudentAnswerByQuestion(ctx, req.AttemptID, req.QuestionID)
	if err != nil {
		return nil, err
	}

	var answer *models.QuizStudentAnswer

	if existingAnswer != nil {
		// Update existing answer
		existingAnswer.AnswerData = answerDataJSON
		if err := s.quizRepo.UpdateStudentAnswer(ctx, existingAnswer); err != nil {
			return nil, fmt.Errorf("failed to update answer: %w", err)
		}
		answer = existingAnswer
	} else {
		// Create new answer
		answer = &models.QuizStudentAnswer{
			AttemptID:  req.AttemptID,
			QuestionID: req.QuestionID,
			AnswerData: answerDataJSON,
		}
		if err := s.quizRepo.CreateStudentAnswer(ctx, answer); err != nil {
			return nil, fmt.Errorf("failed to create answer: %w", err)
		}
	}

	// Auto-grade if possible
	if quiz.AutoGrade && s.canAutoGrade(question.QuestionType) {
		if err := s.autoGradeAnswer(ctx, answer, question); err != nil {
			// Log error but don't fail the submission
			return nil, fmt.Errorf("auto-grade answer: %w", err)
		}
	}

	response := s.buildStudentAnswerResponse(answer)
	response.IsCorrect = nil
	response.PointsEarned = nil
	response.GraderFeedback = ""
	response.GradedBy = nil
	response.GradedAt = nil
	return response, nil
}

// SubmitQuiz submits the entire quiz attempt
func (s *QuizService) submitQuiz(ctx context.Context, attemptID, studentID int64, focus ...*dto.QuizFocusSummary) (*dto.QuizResultResponse, error) {
	// Verify attempt ownership
	attempt, err := s.quizRepo.GetAttempt(ctx, attemptID)
	if err != nil {
		return nil, err
	}

	if attempt == nil {
		return nil, fmt.Errorf("attempt not found")
	}
	if attempt.StudentID != studentID {
		return nil, ErrQuizAccess
	}

	if attempt.Status != models.AttemptStatusInProgress {
		return s.submittedResult(ctx, attempt)
	}

	// Get quiz
	quiz, err := s.quizRepo.GetQuiz(ctx, attempt.QuizID)
	if err != nil {
		return nil, err
	}

	if len(focus) > 0 && focus[0] != nil {
		if focus[0].Departures < 0 || focus[0].Departures > 100000 || focus[0].AwaySeconds < 0 || focus[0].AwaySeconds > 31536000 {
			return nil, fmt.Errorf("invalid focus summary")
		}
		attempt.FocusSummary, err = json.Marshal(focus[0])
		if err != nil {
			return nil, err
		}
	}

	// Calculate time spent
	timeSpent, err := s.quizRepo.GetAttemptElapsedTime(ctx, attemptID)
	if err != nil {
		return nil, fmt.Errorf("failed to calculate elapsed time: %w", err)
	}
	now := time.Now()

	// Update attempt status
	attempt.SubmittedAt = sql.NullTime{Time: now, Valid: true}
	attempt.TimeSpentSeconds = sql.NullInt32{Int32: timeSpent, Valid: true}
	attempt.Status = models.AttemptStatusSubmitted

	// Auto-grade all objective questions
	if quiz.AutoGrade {
		answers, err := s.quizRepo.ListAttemptAnswers(ctx, attemptID)
		if err != nil {
			return nil, err
		}

		allQuestions, err := s.quizRepo.ListQuestionsWithOptions(ctx, quiz.ID)
		if err != nil {
			return nil, err
		}
		s.gradingData = make(map[int64]models.QuestionWithOptions, len(allQuestions))
		for _, question := range allQuestions {
			s.gradingData[question.ID] = question
		}
		for i := range answers {
			question, exists := s.gradingData[answers[i].QuestionID]
			if !exists {
				return nil, fmt.Errorf("question not found for answer")
			}
			if s.canAutoGrade(question.QuestionType) {
				if err := s.autoGradeAnswer(ctx, &answers[i], &question.QuizQuestion); err != nil {
					return nil, err
				}
			}
		}

		attempt.AutoGradedAt = sql.NullTime{Time: now, Valid: true}
	}

	// Calculate total score
	if err := s.calculateAttemptScore(ctx, attempt, quiz); err != nil {
		return nil, fmt.Errorf("failed to calculate score: %w", err)
	}

	if err := s.quizRepo.UpdateAttempt(ctx, attempt); err != nil {
		return nil, fmt.Errorf("failed to submit quiz: %w", err)
	}

	if err := s.quizRepo.EnqueueAttemptEffects(ctx, attempt.ID); err != nil {
		return nil, err
	}
	// Build result response
	return s.submittedResult(ctx, attempt)
}

// GetQuizResult retrieves quiz results
func (s *QuizService) GetQuizResult(ctx context.Context, attemptID, studentID int64) (*dto.QuizResultResponse, error) {
	attempt, err := s.quizRepo.GetAttempt(ctx, attemptID)
	if err != nil {
		return nil, err
	}

	if attempt == nil {
		return nil, fmt.Errorf("attempt not found")
	}
	if attempt.StudentID != studentID {
		return nil, ErrQuizAccess
	}

	if attempt.Status == models.AttemptStatusInProgress {
		return nil, fmt.Errorf("quiz not submitted yet")
	}

	quiz, err := s.quizRepo.GetQuiz(ctx, attempt.QuizID)
	if err != nil {
		return nil, err
	}

	if !quiz.ShowResultsImmediately {
		return nil, fmt.Errorf("results not available yet")
	}

	return s.buildQuizResultResponse(ctx, attempt, quiz)
}

// ReviewQuiz allows student to review their submission
func (s *QuizService) ReviewQuiz(ctx context.Context, attemptID, studentID int64) (*dto.QuizReviewResponse, error) {
	attempt, err := s.quizRepo.GetAttempt(ctx, attemptID)
	if err != nil {
		return nil, err
	}

	if attempt == nil {
		return nil, fmt.Errorf("attempt not found")
	}
	if attempt.StudentID != studentID {
		return nil, ErrQuizAccess
	}

	quiz, err := s.quizRepo.GetQuiz(ctx, attempt.QuizID)
	if err != nil {
		return nil, err
	}

	if !quiz.ShowResultsImmediately {
		return nil, fmt.Errorf("results not available yet")
	}

	if !quiz.AllowReview {
		return nil, fmt.Errorf("review not allowed for this quiz")
	}

	return s.buildQuizReviewResponse(ctx, attempt, quiz)
}
