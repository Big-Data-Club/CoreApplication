package service

import (
	"context"
	"errors"

	"example/hello/internal/models"
)

var ErrQuizAccess = errors.New("permission denied: quiz access required")

type quizAccessReader interface {
	QuizAccess(context.Context, int64, int64) (bool, bool, error)
}

// QuizPolicy separates course-scoped authorization from HTTP and quiz formatting.
// Management is based on ownership/co-teaching, never just a global TEACHER role.
type QuizPolicy struct{ reader quizAccessReader }

func (p QuizPolicy) Check(ctx context.Context, quizID, userID int64, role string) (manager bool, err error) {
	if userID <= 0 {
		return false, ErrQuizAccess
	}
	manage, enrolled, err := p.reader.QuizAccess(ctx, quizID, userID)
	if err != nil {
		return false, err
	}
	if role == "ADMIN" || manage {
		return true, nil
	}
	if !enrolled {
		return false, ErrQuizAccess
	}
	return false, nil
}
func (s *QuizService) authorizeQuizRead(ctx context.Context, quiz *models.Quiz, userID int64, role string) (bool, error) {
	manager, err := (QuizPolicy{s.quizRepo}).Check(ctx, quiz.ID, userID, role)
	if err != nil {
		return false, err
	}
	if !manager && !quiz.IsPublished {
		return false, ErrQuizAccess
	}
	return manager, nil
}
