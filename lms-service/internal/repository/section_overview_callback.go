package repository

import (
	"context"

	"example/hello/internal/dto"
)

func (r *SectionOverviewRepository) SaveGeneratedResults(ctx context.Context, body *dto.SectionOverviewCallbackResults) error {
	return saveCallback(ctx, r.db, "section_overview", body.JobID, body, func(db DBTX) error {
		repo := &SectionOverviewRepository{db: db}
		// Look up the job to get created_by.
		job, err := repo.GetJob(ctx, body.JobID)
		if err != nil {
			return err
		}
		if body.CourseID != job.CourseID || body.SectionID != job.SectionID {
			return ErrCallbackScope
		}

		// Persist lesson.
		if _, err := repo.CreateLesson(
			ctx,
			body.JobID, body.SectionID, body.CourseID, job.CreatedBy,
			body.Lesson.Title, body.Lesson.Summary, body.Lesson.MarkdownContent,
			body.Lesson.References,
		); err != nil {
			return err
		}

		// Persist quiz.
		if _, err := repo.CreateQuiz(
			ctx,
			body.JobID, body.SectionID, body.CourseID, job.CreatedBy,
			body.Quiz.Title, body.Quiz.Summary,
			body.Quiz.QuestionCount,
			body.Quiz.Questions,
			body.Quiz.References,
		); err != nil {
			return err
		}

		return repo.UpdateJobStatus(ctx, body.JobID, "completed", 100, "done", "", "")
	})
}
