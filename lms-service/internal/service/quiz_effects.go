package service

import (
	"context"
	"fmt"
	"time"

	"example/hello/internal/repository"
	"example/hello/pkg/ai"
	"example/hello/pkg/logger"
)

// RunEffects is called by a fixed-size, lifecycle-owned worker pool. Each queue
// row is committed with the submission, so a crash cannot silently lose progress.
func (s *QuizService) RunEffects(ctx context.Context) {
	for ctx.Err() == nil {
		jobCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
		worked, err := s.quizRepo.ProcessNextEffects(jobCtx, func(ctx context.Context, effect repository.QuizEffects) error {
			for _, review := range effect.Reviews {
				if s.aiClient == nil {
					return fmt.Errorf("review delivery unavailable")
				}
				nodeID := review.NodeID
				_, err := s.aiClient.RecordReviewResponse(ctx, ai.RecordReviewRequest{EventID: fmt.Sprintf("lms:answer:%d:%d", review.AnswerID, review.GradedAt.UnixMicro()), StudentID: effect.StudentID, QuestionID: review.QuestionID, CourseID: effect.CourseID, NodeID: &nodeID, Quality: review.Quality})
				if err != nil {
					return err
				}
			}
			return nil
		})
		cancel()
		if err != nil {
			logger.Warn("Quiz effects delivery will retry")
		}
		if !worked || err != nil {
			timer := time.NewTimer(time.Second)
			select {
			case <-ctx.Done():
				timer.Stop()
				return
			case <-timer.C:
			}
		}
	}
}
