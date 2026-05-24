package repository

import (
	"context"
	"database/sql"
	"fmt"

	"example/hello/internal/models"
)

type VideoJobRepository struct {
	db *sql.DB
}

func NewVideoJobRepository(db *sql.DB) *VideoJobRepository {
	return &VideoJobRepository{db: db}
}

// Create inserts a new video generation job.
func (r *VideoJobRepository) Create(ctx context.Context, job *models.VideoGenerationJob) (*models.VideoGenerationJob, error) {
	query := `
		INSERT INTO video_generation_jobs (
			target_type, target_id, custom_prompt, language, template_type,
			created_by, status, progress, retry_count, max_retries, visibility
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
		RETURNING id, created_at, updated_at
	`
	var customPrompt sql.NullString
	if job.CustomPrompt.Valid && job.CustomPrompt.String != "" {
		customPrompt = job.CustomPrompt
	}

	err := r.db.QueryRowContext(ctx, query,
		job.TargetType, job.TargetID, customPrompt, job.Language, job.TemplateType,
		job.CreatedBy, job.Status, job.Progress, job.RetryCount, job.MaxRetries, job.Visibility,
	).Scan(&job.ID, &job.CreatedAt, &job.UpdatedAt)
	if err != nil {
		return nil, fmt.Errorf("create video job repository: %w", err)
	}
	return job, nil
}

// GetByID selects a single job.
func (r *VideoJobRepository) GetByID(ctx context.Context, id string) (*models.VideoGenerationJob, error) {
	query := `
		SELECT id, target_type, target_id, custom_prompt, language, template_type,
		       created_by, status, progress, retry_count, max_retries,
		       last_error_message, last_error_at, youtube_video_id, youtube_url,
		       visibility, created_at, updated_at
		FROM video_generation_jobs
		WHERE id = $1
	`
	var j models.VideoGenerationJob
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&j.ID, &j.TargetType, &j.TargetID, &j.CustomPrompt, &j.Language, &j.TemplateType,
		&j.CreatedBy, &j.Status, &j.Progress, &j.RetryCount, &j.MaxRetries,
		&j.LastErrorMessage, &j.LastErrorAt, &j.YoutubeVideoID, &j.YoutubeURL,
		&j.Visibility, &j.CreatedAt, &j.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	return &j, nil
}

// ListByTarget lists jobs for a course or section.
func (r *VideoJobRepository) ListByTarget(ctx context.Context, targetType string, targetID int64) ([]*models.VideoGenerationJob, error) {
	query := `
		SELECT id, target_type, target_id, custom_prompt, language, template_type,
		       created_by, status, progress, retry_count, max_retries,
		       last_error_message, last_error_at, youtube_video_id, youtube_url,
		       visibility, created_at, updated_at
		FROM video_generation_jobs
		WHERE target_type = $1 AND target_id = $2
		ORDER BY created_at DESC
	`
	rows, err := r.db.QueryContext(ctx, query, targetType, targetID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var jobs []*models.VideoGenerationJob
	for rows.Next() {
		var j models.VideoGenerationJob
		err := rows.Scan(
			&j.ID, &j.TargetType, &j.TargetID, &j.CustomPrompt, &j.Language, &j.TemplateType,
			&j.CreatedBy, &j.Status, &j.Progress, &j.RetryCount, &j.MaxRetries,
			&j.LastErrorMessage, &j.LastErrorAt, &j.YoutubeVideoID, &j.YoutubeURL,
			&j.Visibility, &j.CreatedAt, &j.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}
		jobs = append(jobs, &j)
	}
	return jobs, rows.Err()
}

// ListByUser lists all jobs created by a user.
func (r *VideoJobRepository) ListByUser(ctx context.Context, userID int64) ([]*models.VideoGenerationJob, error) {
	query := `
		SELECT id, target_type, target_id, custom_prompt, language, template_type,
		       created_by, status, progress, retry_count, max_retries,
		       last_error_message, last_error_at, youtube_video_id, youtube_url,
		       visibility, created_at, updated_at
		FROM video_generation_jobs
		WHERE created_by = $1
		ORDER BY created_at DESC
	`
	rows, err := r.db.QueryContext(ctx, query, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var jobs []*models.VideoGenerationJob
	for rows.Next() {
		var j models.VideoGenerationJob
		err := rows.Scan(
			&j.ID, &j.TargetType, &j.TargetID, &j.CustomPrompt, &j.Language, &j.TemplateType,
			&j.CreatedBy, &j.Status, &j.Progress, &j.RetryCount, &j.MaxRetries,
			&j.LastErrorMessage, &j.LastErrorAt, &j.YoutubeVideoID, &j.YoutubeURL,
			&j.Visibility, &j.CreatedAt, &j.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}
		jobs = append(jobs, &j)
	}
	return jobs, rows.Err()
}

// UpdateStatus updates the job status and progress.
func (r *VideoJobRepository) UpdateStatus(ctx context.Context, id string, status string, progress int) error {
	query := `
		UPDATE video_generation_jobs
		SET status = $2, progress = $3, updated_at = NOW()
		WHERE id = $1
	`
	_, err := r.db.ExecContext(ctx, query, id, status, progress)
	return err
}

// UpdateYouTubeInfo updates YouTube video credentials.
func (r *VideoJobRepository) UpdateYouTubeInfo(ctx context.Context, id string, ytVideoID string, ytURL string) error {
	query := `
		UPDATE video_generation_jobs
		SET youtube_video_id = $2, youtube_url = $3, updated_at = NOW()
		WHERE id = $1
	`
	_, err := r.db.ExecContext(ctx, query, id, ytVideoID, ytURL)
	return err
}

// UpdateError logs failure metadata.
func (r *VideoJobRepository) UpdateError(ctx context.Context, id string, errMsg string, retryCount int) error {
	query := `
		UPDATE video_generation_jobs
		SET status = 'FAILED', last_error_message = $2, last_error_at = NOW(), retry_count = $3, updated_at = NOW()
		WHERE id = $1
	`
	_, err := r.db.ExecContext(ctx, query, id, errMsg, retryCount)
	return err
}

// CountActiveJobs counts jobs in PENDING, PLANNING, SCRIPTING, RENDERING, or UPLOADING states.
func (r *VideoJobRepository) CountActiveJobs(ctx context.Context, userID int64) (int, error) {
	query := `
		SELECT COUNT(*)
		FROM video_generation_jobs
		WHERE created_by = $1 AND status IN ('PENDING', 'PLANNING', 'SCRIPTING', 'RENDERING', 'UPLOADING', 'PUBLISHING')
	`
	var count int
	err := r.db.QueryRowContext(ctx, query, userID).Scan(&count)
	return count, err
}

// CountDailyJobs counts jobs created by user today.
func (r *VideoJobRepository) CountDailyJobs(ctx context.Context, userID int64) (int, error) {
	query := `
		SELECT COUNT(*)
		FROM video_generation_jobs
		WHERE created_by = $1 AND created_at >= NOW() - INTERVAL '1 day'
	`
	var count int
	err := r.db.QueryRowContext(ctx, query, userID).Scan(&count)
	return count, err
}

// LockAndGetForPublish locks the row for updates (idempotency check).
func (r *VideoJobRepository) LockAndGetForPublish(ctx context.Context, tx *sql.Tx, id string) (*models.VideoGenerationJob, error) {
	query := `
		SELECT id, target_type, target_id, custom_prompt, language, template_type,
		       created_by, status, progress, retry_count, max_retries,
		       last_error_message, last_error_at, youtube_video_id, youtube_url,
		       visibility, created_at, updated_at
		FROM video_generation_jobs
		WHERE id = $1
		FOR UPDATE
	`
	var j models.VideoGenerationJob
	var err error
	if tx != nil {
		err = tx.QueryRowContext(ctx, query, id).Scan(
			&j.ID, &j.TargetType, &j.TargetID, &j.CustomPrompt, &j.Language, &j.TemplateType,
			&j.CreatedBy, &j.Status, &j.Progress, &j.RetryCount, &j.MaxRetries,
			&j.LastErrorMessage, &j.LastErrorAt, &j.YoutubeVideoID, &j.YoutubeURL,
			&j.Visibility, &j.CreatedAt, &j.UpdatedAt,
		)
	} else {
		err = r.db.QueryRowContext(ctx, query, id).Scan(
			&j.ID, &j.TargetType, &j.TargetID, &j.CustomPrompt, &j.Language, &j.TemplateType,
			&j.CreatedBy, &j.Status, &j.Progress, &j.RetryCount, &j.MaxRetries,
			&j.LastErrorMessage, &j.LastErrorAt, &j.YoutubeVideoID, &j.YoutubeURL,
			&j.Visibility, &j.CreatedAt, &j.UpdatedAt,
		)
	}
	if err != nil {
		return nil, err
	}
	return &j, nil
}

// SetPublishing sets the status to PUBLISHING inside a transaction.
func (r *VideoJobRepository) SetPublishing(ctx context.Context, tx *sql.Tx, id string) error {
	query := `
		UPDATE video_generation_jobs
		SET status = 'PUBLISHING', updated_at = NOW()
		WHERE id = $1
	`
	var err error
	if tx != nil {
		_, err = tx.ExecContext(ctx, query, id)
	} else {
		_, err = r.db.ExecContext(ctx, query, id)
	}
	return err
}

// SetPublic sets status to PUBLIC and visibility to public.
func (r *VideoJobRepository) SetPublic(ctx context.Context, id string) error {
	query := `
		UPDATE video_generation_jobs
		SET status = 'PUBLIC', visibility = 'public', updated_at = NOW()
		WHERE id = $1
	`
	_, err := r.db.ExecContext(ctx, query, id)
	return err
}
