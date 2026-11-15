package repository

import (
	"context"
	"database/sql"
	"fmt"

	"example/hello/internal/models"
)

type MicroLessonRepository struct {
	db DBTX
}

func NewMicroLessonRepository(db *sql.DB) *MicroLessonRepository {
	return &MicroLessonRepository{db: db}
}

// ── Jobs ──────────────────────────────────────────────────────────

func (r *MicroLessonRepository) CreateJob(ctx context.Context, job *models.MicroLessonJob) (*models.MicroLessonJob, error) {
	query := `
		INSERT INTO micro_lesson_jobs (
			course_id, section_id, source_content_id,
			source_file_path, source_file_type, source_url,
			target_minutes, language, status, created_by
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
		RETURNING id, created_at, updated_at
	`
	err := r.db.QueryRowContext(ctx, query,
		job.CourseID, job.SectionID, job.SourceContentID,
		job.SourceFilePath, job.SourceFileType, job.SourceURL,
		job.TargetMinutes, job.Language, job.Status, job.CreatedBy,
	).Scan(&job.ID, &job.CreatedAt, &job.UpdatedAt)
	if err != nil {
		return nil, fmt.Errorf("create micro_lesson_job: %w", err)
	}
	return job, nil
}

func (r *MicroLessonRepository) GetJob(ctx context.Context, id int64) (*models.MicroLessonJob, error) {
	query := `
		SELECT id, course_id, section_id, source_content_id,
		       source_file_path, source_file_type, source_url,
		       target_minutes, language, status, progress, stage,
		       lessons_count, error, created_by, created_at, updated_at, completed_at
		FROM micro_lesson_jobs
		WHERE id = $1
	`
	var j models.MicroLessonJob
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&j.ID, &j.CourseID, &j.SectionID, &j.SourceContentID,
		&j.SourceFilePath, &j.SourceFileType, &j.SourceURL,
		&j.TargetMinutes, &j.Language, &j.Status, &j.Progress, &j.Stage,
		&j.LessonsCount, &j.Error, &j.CreatedBy, &j.CreatedAt, &j.UpdatedAt, &j.CompletedAt,
	)
	if err != nil {
		return nil, err
	}
	return &j, nil
}

func (r *MicroLessonRepository) ListJobsByCourse(ctx context.Context, courseID int64) ([]*models.MicroLessonJob, error) {
	query := `
		SELECT id, course_id, section_id, source_content_id,
		       source_file_path, source_file_type, source_url,
		       target_minutes, language, status, progress, stage,
		       lessons_count, error, created_by, created_at, updated_at, completed_at
		FROM micro_lesson_jobs
		WHERE course_id = $1
		ORDER BY created_at DESC
	`
	rows, err := r.db.QueryContext(ctx, query, courseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var jobs []*models.MicroLessonJob
	for rows.Next() {
		var j models.MicroLessonJob
		if err := rows.Scan(
			&j.ID, &j.CourseID, &j.SectionID, &j.SourceContentID,
			&j.SourceFilePath, &j.SourceFileType, &j.SourceURL,
			&j.TargetMinutes, &j.Language, &j.Status, &j.Progress, &j.Stage,
			&j.LessonsCount, &j.Error, &j.CreatedBy, &j.CreatedAt, &j.UpdatedAt, &j.CompletedAt,
		); err != nil {
			return nil, err
		}
		jobs = append(jobs, &j)
	}
	return jobs, rows.Err()
}

// UpdateJobStatus is called by the AI service callback when a job changes state.
func (r *MicroLessonRepository) UpdateJobStatus(
	ctx context.Context,
	jobID int64,
	status string,
	progress int,
	stage string,
	lessonsCount int,
	errMsg string,
) error {
	var nullErr sql.NullString
	if errMsg != "" {
		nullErr = sql.NullString{String: errMsg, Valid: true}
	}
	query := `
		UPDATE micro_lesson_jobs
		SET status = $2, progress = $3, stage = $4, lessons_count = $5,
		    error = $6, updated_at = NOW(),
		    completed_at = CASE WHEN $2::varchar IN ('completed','failed') THEN NOW() ELSE completed_at END
		WHERE id = $1 AND (status NOT IN ('completed','failed') OR status = $2)
	`
	_, err := r.db.ExecContext(ctx, query, jobID, status, progress, stage, lessonsCount, nullErr)
	return err
}

// ── Lessons ───────────────────────────────────────────────────────

// CreateLesson inserts a single lesson row (called by AI service callback).
func (r *MicroLessonRepository) CreateLesson(ctx context.Context, lesson *models.MicroLesson) (*models.MicroLesson, error) {
	query := `
		INSERT INTO micro_lessons (
			job_id, course_id, section_id, source_content_id,
			title, summary, objectives, markdown_content,
			estimated_minutes, order_index, status, node_id, image_urls,
			language, created_by
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
		RETURNING id, created_at, updated_at
	`
	if lesson.Objectives == nil {
		lesson.Objectives = []byte(`[]`)
	}
	if lesson.ImageURLs == nil {
		lesson.ImageURLs = []byte(`[]`)
	}
	if lesson.Status == "" {
		lesson.Status = models.MicroLessonStatusDraft
	}
	err := r.db.QueryRowContext(ctx, query,
		lesson.JobID, lesson.CourseID, lesson.SectionID, lesson.SourceContentID,
		lesson.Title, lesson.Summary, string(lesson.Objectives), lesson.MarkdownContent,
		lesson.EstimatedMinutes, lesson.OrderIndex, lesson.Status, lesson.NodeID, string(lesson.ImageURLs),
		lesson.Language, lesson.CreatedBy,
	).Scan(&lesson.ID, &lesson.CreatedAt, &lesson.UpdatedAt)
	if err != nil {
		return nil, fmt.Errorf("create micro_lesson: %w", err)
	}
	return lesson, nil
}

func (r *MicroLessonRepository) GetLesson(ctx context.Context, id int64) (*models.MicroLesson, error) {
	query := `
		SELECT id, job_id, course_id, section_id, source_content_id,
		       title, summary, objectives, markdown_content,
		       estimated_minutes, order_index, status, published_content_id,
		       node_id, image_urls, language, created_by, created_at, updated_at, published_at
		FROM micro_lessons
		WHERE id = $1
	`
	var l models.MicroLesson
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&l.ID, &l.JobID, &l.CourseID, &l.SectionID, &l.SourceContentID,
		&l.Title, &l.Summary, &l.Objectives, &l.MarkdownContent,
		&l.EstimatedMinutes, &l.OrderIndex, &l.Status, &l.PublishedContentID,
		&l.NodeID, &l.ImageURLs, &l.Language, &l.CreatedBy, &l.CreatedAt, &l.UpdatedAt, &l.PublishedAt,
	)
	if err != nil {
		return nil, err
	}
	return &l, nil
}

func (r *MicroLessonRepository) ListLessonsByJob(ctx context.Context, jobID int64) ([]*models.MicroLesson, error) {
	return r.listLessonsBy(ctx, "job_id = $1 ORDER BY order_index ASC, id ASC", jobID)
}

func (r *MicroLessonRepository) ListLessonsByCourse(ctx context.Context, courseID int64) ([]*models.MicroLesson, error) {
	return r.listLessonsBy(ctx,
		"course_id = $1 ORDER BY job_id DESC, order_index ASC, id ASC",
		courseID,
	)
}

func (r *MicroLessonRepository) listLessonsBy(ctx context.Context, where string, args ...interface{}) ([]*models.MicroLesson, error) {
	query := `
		SELECT id, job_id, course_id, section_id, source_content_id,
		       title, summary, objectives, markdown_content,
		       estimated_minutes, order_index, status, published_content_id,
		       node_id, image_urls, language, created_by, created_at, updated_at, published_at
		FROM micro_lessons
		WHERE ` + where
	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var lessons []*models.MicroLesson
	for rows.Next() {
		var l models.MicroLesson
		if err := rows.Scan(
			&l.ID, &l.JobID, &l.CourseID, &l.SectionID, &l.SourceContentID,
			&l.Title, &l.Summary, &l.Objectives, &l.MarkdownContent,
			&l.EstimatedMinutes, &l.OrderIndex, &l.Status, &l.PublishedContentID,
			&l.NodeID, &l.ImageURLs, &l.Language, &l.CreatedBy, &l.CreatedAt, &l.UpdatedAt, &l.PublishedAt,
		); err != nil {
			return nil, err
		}
		lessons = append(lessons, &l)
	}
	return lessons, rows.Err()
}

// UpdateLessonContent saves an instructor's edits to title/markdown/objectives/etc.
func (r *MicroLessonRepository) UpdateLessonContent(
	ctx context.Context,
	id int64,
	title string,
	summary sql.NullString,
	objectives []byte,
	markdown string,
	estimatedMinutes int,
	orderIndex int,
) error {
	if objectives == nil {
		objectives = []byte(`[]`)
	}
	query := `
		UPDATE micro_lessons
		SET title = $2, summary = $3, objectives = $4,
		    markdown_content = $5, estimated_minutes = $6, order_index = $7,
		    updated_at = NOW()
		WHERE id = $1
	`
	_, err := r.db.ExecContext(ctx, query, id, title, summary, string(objectives), markdown, estimatedMinutes, orderIndex)
	return err
}

// MarkPublished records that the lesson has been promoted into a SectionContent.
func (r *MicroLessonRepository) MarkPublished(ctx context.Context, lessonID, sectionContentID int64) error {
	query := `
		UPDATE micro_lessons
		SET status = 'published',
		    published_content_id = $2,
		    published_at = NOW(),
		    updated_at = NOW()
		WHERE id = $1
	`
	_, err := r.db.ExecContext(ctx, query, lessonID, sectionContentID)
	return err
}

func (r *MicroLessonRepository) DeleteLesson(ctx context.Context, id int64) error {
	_, err := r.db.ExecContext(ctx, "DELETE FROM micro_lessons WHERE id = $1", id)
	return err
}
