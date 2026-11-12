package service

import (
	"context"
	"encoding/json"
	"fmt"

	"example/hello/internal/dto"
)

func (s *QuizService) AuthorizeQuizResults(ctx context.Context, quizID, userID int64, role string) error {
	if _, err := s.quizRepo.GetQuiz(ctx, quizID); err != nil {
		return err
	}
	return s.verifyQuizOwnership(ctx, quizID, userID, role)
}

func (s *QuizService) GetQuizResults(ctx context.Context, quizID, userID int64, role string, options ...dto.QuizResultsQuery) (json.RawMessage, error) {
	if err := s.AuthorizeQuizResults(ctx, quizID, userID, role); err != nil {
		return nil, err
	}
	return s.quizRepo.GetQuizResults(ctx, quizID, options...)
}

func (s *QuizService) GetTeacherAttemptResults(ctx context.Context, quizID, attemptID, userID int64, role string) (interface{}, error) {
	if err := s.AuthorizeQuizResults(ctx, quizID, userID, role); err != nil {
		return nil, err
	}
	attempt, err := s.quizRepo.GetAttempt(ctx, attemptID)
	if err != nil {
		return nil, err
	}
	if attempt.QuizID != quizID {
		return nil, fmt.Errorf("attempt does not belong to quiz")
	}
	answers, err := s.quizRepo.GetAttemptAnswers(ctx, attemptID)
	if err != nil {
		return nil, err
	}
	return dto.ToQuizStudentAnswerDTOList(answers), nil
}

func (s *QuizService) GetQuizResultRows(ctx context.Context, quizID, userID int64, role string, q dto.QuizResultsQuery) (json.RawMessage, error) {
	if err := s.AuthorizeQuizResults(ctx, quizID, userID, role); err != nil {
		return nil, err
	}
	return s.quizRepo.GetQuizResultRows(ctx, quizID, q)
}
