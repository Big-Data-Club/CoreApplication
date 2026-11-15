package service

import (
	"context"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
)

func (s *QuizService) StartQuizAttempt(ctx context.Context, quizID, studentID int64, ip, userAgent string) (response *dto.QuizAttemptResponse, err error) {
	err = s.quizRepo.WithStartLock(ctx, quizID, studentID, func(repo *repository.QuizRepository) error {
		scoped := *s
		scoped.quizRepo = repo
		var failure error
		response, failure = scoped.startQuizAttempt(ctx, quizID, studentID, ip, userAgent)
		return failure
	})
	return
}
func (s *QuizService) SubmitAnswer(ctx context.Context, req *dto.SubmitAnswerRequest, studentID int64) (response *dto.StudentAnswerResponse, err error) {
	err = s.quizRepo.WithAttemptLock(ctx, req.AttemptID, func(repo *repository.QuizRepository) error {
		scoped := *s
		scoped.quizRepo = repo
		var failure error
		response, failure = scoped.submitAnswer(ctx, req, studentID)
		return failure
	})
	return
}
func (s *QuizService) SubmitQuiz(ctx context.Context, attemptID, studentID int64, focus ...*dto.QuizFocusSummary) (response *dto.QuizResultResponse, err error) {
	err = s.quizRepo.WithAttemptLock(ctx, attemptID, func(repo *repository.QuizRepository) error {
		scoped := *s
		scoped.quizRepo = repo
		var failure error
		response, failure = scoped.submitQuiz(ctx, attemptID, studentID, focus...)
		return failure
	})
	return
}
func (s *QuizService) submittedResult(ctx context.Context, attempt *models.QuizAttempt) (*dto.QuizResultResponse, error) {
	quiz, err := s.quizRepo.GetQuiz(ctx, attempt.QuizID)
	if err != nil {
		return nil, err
	}
	if !quiz.ShowResultsImmediately {
		response := s.buildAttemptResponse(attempt)
		response.EarnedPoints = nil
		response.Percentage = nil
		response.IsPassed = nil
		return &dto.QuizResultResponse{Attempt: *response, Quiz: *s.buildQuizResponse(quiz)}, nil
	}
	return s.buildQuizResultResponse(ctx, attempt, quiz)
}
func (s *QuizService) gradingOptions(ctx context.Context, id int64) ([]models.QuizAnswerOption, error) {
	if q, ok := s.gradingData[id]; ok {
		return q.AnswerOptions, nil
	}
	return s.quizRepo.ListAnswerOptions(ctx, id)
}
func (s *QuizService) gradingCorrectAnswers(ctx context.Context, id int64) ([]models.QuizCorrectAnswer, error) {
	if q, ok := s.gradingData[id]; ok {
		return q.CorrectAnswers, nil
	}
	return s.quizRepo.ListCorrectAnswers(ctx, id)
}

func (s *QuizService) GradeAnswer(ctx context.Context, req *dto.GradeAnswerRequest, userID int64, role string) error {
	answer, err := s.quizRepo.GetStudentAnswer(ctx, req.AnswerID)
	if err != nil {
		return err
	}
	// Verify management before holding a transaction; the resource ID is resolved server-side.
	attempt, err := s.quizRepo.GetAttempt(ctx, answer.AttemptID)
	if err != nil {
		return err
	}
	if err := s.verifyQuizOwnership(ctx, attempt.QuizID, userID, role); err != nil {
		return err
	}
	return s.quizRepo.WithAttemptLock(ctx, answer.AttemptID, func(repo *repository.QuizRepository) error {
		scoped := *s
		scoped.quizRepo = repo
		return scoped.gradeAnswer(ctx, req, userID, role)
	})
}
