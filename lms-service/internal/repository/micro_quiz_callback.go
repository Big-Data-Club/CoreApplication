package repository

import (
	"context"
	"database/sql"

	"example/hello/internal/dto"
	"example/hello/internal/models"
)

func (r *MicroQuizRepository) SaveGeneratedQuizzes(ctx context.Context, body *dto.MicroQuizzesCallback) error {
	return saveCallback(ctx, r.db, "micro_quizzes", body.JobID, body, func(db DBTX) error {
		repo := &MicroQuizRepository{db: db}
		job, err := repo.GetJob(ctx, body.JobID)
		if err != nil {
			return err
		}
		if body.CourseID != job.CourseID {
			return ErrCallbackScope
		}
		if body.SourceContentID != nil && (!job.SourceContentID.Valid || *body.SourceContentID != job.SourceContentID.Int64) {
			return ErrCallbackScope
		}

		for _, item := range body.Quizzes {
			questionsBytes := []byte(item.QuestionsJSON)
			if len(questionsBytes) == 0 {
				questionsBytes = []byte("[]")
			}
			quiz := &models.MicroQuiz{
				JobID:          body.JobID,
				CourseID:       job.CourseID,
				SectionID:      job.SectionID,
				Title:          item.Title,
				Summary:        sql.NullString{String: item.Summary, Valid: item.Summary != ""},
				QuestionsJSON:  questionsBytes,
				QuestionsCount: item.QuestionsCount,
				OrderIndex:     item.OrderIndex,
				Language:       job.Language,
				CreatedBy:      job.CreatedBy,
			}
			quiz.SourceContentID = job.SourceContentID
			if item.NodeID != nil {
				quiz.NodeID = sql.NullInt64{Int64: *item.NodeID, Valid: true}
			}

			if _, err := repo.CreateQuiz(ctx, quiz); err != nil {
				return err
			}
		}
		return repo.UpdateJobStatus(ctx, body.JobID, "completed", 100, "done", len(body.Quizzes), "")
	})
}
