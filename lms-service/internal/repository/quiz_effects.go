package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"
)

type QuizEffects struct {
	AttemptID, QuizID, ContentID, StudentID, CourseID int64
	Reviews                                           []QuizReviewEffect
}
type QuizReviewEffect struct {
	AnswerID, QuestionID, NodeID int64
	Quality                      int
	GradedAt                     time.Time
}

// ProcessNextEffects locks one queue row; only a bounded worker calls this method.
func (r *QuizRepository) ProcessNextEffects(ctx context.Context, deliver func(context.Context, QuizEffects) error) (bool, error) {
	prepared, err := r.prepareNextLocalEffects(ctx)
	if err != nil {
		return prepared, err
	}

	tx, err := beginTransaction(ctx, r.db)
	if err != nil {
		return false, err
	}
	defer tx.Rollback()
	var effect QuizEffects
	err = tx.QueryRowContext(ctx, `SELECT attempt_id FROM lms_quiz_effects WHERE local_completed_at IS NOT NULL AND completed_at IS NULL AND available_at<=now() ORDER BY available_at,attempt_id FOR UPDATE SKIP LOCKED LIMIT 1`).Scan(&effect.AttemptID)
	if errors.Is(err, sql.ErrNoRows) {
		return prepared, nil
	}
	if err != nil {
		return false, err
	}
	scoped := &QuizRepository{db: tx}
	attempt, err := scoped.GetAttempt(ctx, effect.AttemptID)
	if err != nil {
		return true, err
	}
	quiz, err := scoped.GetQuiz(ctx, attempt.QuizID)
	if err != nil {
		return true, err
	}
	effect.QuizID = quiz.ID
	effect.StudentID = attempt.StudentID
	effect.ContentID = quiz.ContentID
	effect.CourseID, err = scoped.GetQuizCourseID(ctx, quiz.ID)
	if err != nil {
		return true, err
	}
	answers, err := scoped.ListAttemptAnswers(ctx, attempt.ID)
	if err != nil {
		return true, err
	}
	questions, err := scoped.ListQuestions(ctx, quiz.ID)
	if err != nil {
		return true, err
	}
	nodes := make(map[int64]int64, len(questions))
	for _, q := range questions {
		if q.NodeID.Valid {
			nodes[q.ID] = q.NodeID.Int64
		}
	}
	for _, answer := range answers {
		if nodeID := nodes[answer.QuestionID]; nodeID > 0 && answer.IsCorrect.Valid && answer.GradedAt.Valid {
			quality := 1
			if answer.IsCorrect.Bool {
				quality = 4
			}
			effect.Reviews = append(effect.Reviews, QuizReviewEffect{answer.ID, answer.QuestionID, nodeID, quality, answer.GradedAt.Time})
		}
	}
	if err = deliver(ctx, effect); err != nil {
		// Do not store internal upstream response bodies or user data in job errors.
		_, failure := tx.ExecContext(ctx, `UPDATE lms_quiz_effects SET attempts=attempts+1,last_error='delivery failed',available_at=now()+LEAST(300,POWER(2,LEAST(attempts,8))) * interval '1 second' WHERE attempt_id=$1`, attempt.ID)
		if failure != nil {
			return true, failure
		}
		if commitErr := tx.Commit(); commitErr != nil {
			return true, commitErr
		}
		return true, err
	}
	if _, err := tx.ExecContext(ctx, `UPDATE lms_quiz_effects SET completed_at=now(),last_error='' WHERE attempt_id=$1`, attempt.ID); err != nil {
		return true, err
	}
	return true, tx.Commit()
}

// Local effects never wait for AI availability. They commit before remote delivery.
func (r *QuizRepository) prepareNextLocalEffects(ctx context.Context) (bool, error) {
	tx, err := beginTransaction(ctx, r.db)
	if err != nil {
		return false, err
	}
	defer tx.Rollback()
	var id int64
	err = tx.QueryRowContext(ctx, `SELECT attempt_id FROM lms_quiz_effects WHERE local_completed_at IS NULL ORDER BY attempt_id FOR UPDATE SKIP LOCKED LIMIT 1`).Scan(&id)
	if errors.Is(err, sql.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	scoped := &QuizRepository{db: tx}
	attempt, err := scoped.GetAttempt(ctx, id)
	if err != nil {
		return true, err
	}
	quiz, err := scoped.GetQuiz(ctx, attempt.QuizID)
	if err != nil {
		return true, err
	}
	if quiz.ContentID > 0 {
		if _, err := tx.ExecContext(ctx, `INSERT INTO content_progress(content_id,student_id) VALUES($1,$2) ON CONFLICT DO NOTHING`, quiz.ContentID, attempt.StudentID); err != nil {
			return true, err
		}
	}
	if _, err := tx.ExecContext(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1,0))`, fmt.Sprintf("quiz-analytics:%d", quiz.ID)); err != nil {
		return true, err
	}
	if err := scoped.UpdateQuizAnalytics(ctx, quiz.ID); err != nil {
		return true, err
	}
	if _, err := tx.ExecContext(ctx, `UPDATE lms_quiz_effects SET local_completed_at=now() WHERE attempt_id=$1`, id); err != nil {
		return true, err
	}
	return true, tx.Commit()
}
