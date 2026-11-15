package repository

import (
	"context"
	"database/sql"
	"encoding/json"

	"example/hello/internal/dto"
	"example/hello/internal/models"
)

func (r *MicroLessonRepository) SaveGeneratedLessons(ctx context.Context, body *dto.MicroLessonsCallback) error {
	return saveCallback(ctx, r.db, "micro_lessons", body.JobID, body, func(db DBTX) error {
		repo := &MicroLessonRepository{db: db}
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

		if body.SectionID != nil && (!job.SectionID.Valid || *body.SectionID != job.SectionID.Int64) {
			return ErrCallbackScope
		}
		for _, l := range body.Lessons {
			objectives, _ := json.Marshal(l.Objectives)
			images, _ := json.Marshal(l.ImageURLs)
			summary := sql.NullString{}
			if l.Summary != "" {
				summary = sql.NullString{String: l.Summary, Valid: true}
			}

			lesson := &models.MicroLesson{
				JobID:            body.JobID,
				CourseID:         job.CourseID,
				Title:            l.Title,
				Summary:          summary,
				Objectives:       objectives,
				MarkdownContent:  l.MarkdownContent,
				EstimatedMinutes: l.EstimatedMinutes,
				OrderIndex:       l.OrderIndex,
				ImageURLs:        images,
				Language:         job.Language,
				CreatedBy:        job.CreatedBy,
			}
			lesson.SectionID = job.SectionID
			lesson.SourceContentID = job.SourceContentID
			if l.NodeID != nil {
				lesson.NodeID = sql.NullInt64{Int64: *l.NodeID, Valid: true}
			}
			if _, err := repo.CreateLesson(ctx, lesson); err != nil {
				return err
			}
		}
		return repo.UpdateJobStatus(ctx, body.JobID, "completed", 100, "done", len(body.Lessons), "")
	})
}
