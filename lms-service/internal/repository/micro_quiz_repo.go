package repository

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"example/hello/internal/models"
)

// MicroQuizRepository handles CRUD for micro_quiz_jobs and micro_quizzes.
type MicroQuizRepository struct {
	db *sql.DB
}

// NewMicroQuizRepository creates a new MicroQuizRepository.
func NewMicroQuizRepository(db *sql.DB) *MicroQuizRepository {
	return &MicroQuizRepository{db: db}
}

// ── Jobs ──────────────────────────────────────────────────────────────────────

// CreateJob inserts a new micro quiz job and returns the generated ID.
func (r *MicroQuizRepository) CreateJob(ctx context.Context, job *models.MicroQuizJob) (int64, error) {
	const q = `
	INSERT INTO micro_quiz_jobs
		(course_id, section_id, source_content_id, source_file_path, source_file_type,
		 source_url, language, status, created_by)
	VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
	RETURNING id`

	var id int64
	err := r.db.QueryRowContext(ctx, q,
		job.CourseID,
		job.SectionID,
		job.SourceContentID,
		job.SourceFilePath,
		job.SourceFileType,
		job.SourceURL,
		job.Language,
		models.MicroQuizJobStatusQueued,
		job.CreatedBy,
	).Scan(&id)
	return id, err
}

// GetJob returns a single job by ID.
func (r *MicroQuizRepository) GetJob(ctx context.Context, jobID int64) (*models.MicroQuizJob, error) {
	const q = `SELECT * FROM micro_quiz_jobs WHERE id = $1`
	var j models.MicroQuizJob
	err := r.db.QueryRowContext(ctx, q, jobID).Scan(
		&j.ID, &j.CourseID, &j.SectionID, &j.SourceContentID,
		&j.SourceFilePath, &j.SourceFileType, &j.SourceURL,
		&j.Language, &j.Status, &j.Progress, &j.Stage,
		&j.QuizzesCount, &j.Error, &j.CreatedBy,
		&j.CreatedAt, &j.UpdatedAt, &j.CompletedAt,
	)
	if err != nil {
		return nil, err
	}
	return &j, nil
}

// ListJobsByCourse returns all jobs for a course, newest first.
func (r *MicroQuizRepository) ListJobsByCourse(ctx context.Context, courseID int64) ([]models.MicroQuizJob, error) {
	const q = `SELECT * FROM micro_quiz_jobs WHERE course_id = $1 ORDER BY id DESC LIMIT 50`
	rows, err := r.db.QueryContext(ctx, q, courseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var jobs []models.MicroQuizJob
	for rows.Next() {
		var j models.MicroQuizJob
		if err := rows.Scan(
			&j.ID, &j.CourseID, &j.SectionID, &j.SourceContentID,
			&j.SourceFilePath, &j.SourceFileType, &j.SourceURL,
			&j.Language, &j.Status, &j.Progress, &j.Stage,
			&j.QuizzesCount, &j.Error, &j.CreatedBy,
			&j.CreatedAt, &j.UpdatedAt, &j.CompletedAt,
		); err != nil {
			return nil, err
		}
		jobs = append(jobs, j)
	}
	return jobs, rows.Err()
}

// UpdateJobStatus updates the status fields of a job (used by AI callback).
func (r *MicroQuizRepository) UpdateJobStatus(
	ctx context.Context,
	jobID int64, status string, progress int, stage string,
	quizzesCount int, errMsg string,
) error {
	var completedAt sql.NullTime
	if status == models.MicroQuizJobStatusCompleted || status == models.MicroQuizJobStatusFailed {
		completedAt = sql.NullTime{Time: time.Now(), Valid: true}
	}

	const q = `
	UPDATE micro_quiz_jobs
	SET status = $2, progress = $3, stage = $4, quizzes_count = $5,
	    error = CASE WHEN $6 = '' THEN error ELSE $6 END,
	    completed_at = $7
	WHERE id = $1`

	_, err := r.db.ExecContext(ctx, q,
		jobID, status, progress, stage, quizzesCount, errMsg, completedAt,
	)
	return err
}

// ── Quizzes ───────────────────────────────────────────────────────────────────

// CreateQuiz inserts a new micro quiz.
func (r *MicroQuizRepository) CreateQuiz(ctx context.Context, quiz *models.MicroQuiz) (int64, error) {
	const q = `
	INSERT INTO micro_quizzes
		(job_id, course_id, section_id, source_content_id,
		 title, summary, questions_json, questions_count,
		 order_index, status, node_id, language, created_by)
	VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
	RETURNING id`

	var id int64
	err := r.db.QueryRowContext(ctx, q,
		quiz.JobID, quiz.CourseID, quiz.SectionID, quiz.SourceContentID,
		quiz.Title, quiz.Summary, quiz.QuestionsJSON, quiz.QuestionsCount,
		quiz.OrderIndex, models.MicroQuizStatusDraft,
		quiz.NodeID, quiz.Language, quiz.CreatedBy,
	).Scan(&id)
	return id, err
}

// GetQuiz returns a single quiz by ID.
func (r *MicroQuizRepository) GetQuiz(ctx context.Context, quizID int64) (*models.MicroQuiz, error) {
	const q = `SELECT * FROM micro_quizzes WHERE id = $1`
	var mq models.MicroQuiz
	err := r.db.QueryRowContext(ctx, q, quizID).Scan(
		&mq.ID, &mq.JobID, &mq.CourseID, &mq.SectionID, &mq.SourceContentID,
		&mq.Title, &mq.Summary, &mq.QuestionsJSON, &mq.QuestionsCount,
		&mq.OrderIndex, &mq.Status, &mq.PublishedContentID,
		&mq.NodeID, &mq.Language, &mq.CreatedBy,
		&mq.CreatedAt, &mq.UpdatedAt, &mq.PublishedAt,
	)
	if err != nil {
		return nil, err
	}
	return &mq, nil
}

// ListQuizzesByJob returns all quizzes for a given job.
func (r *MicroQuizRepository) ListQuizzesByJob(ctx context.Context, jobID int64) ([]models.MicroQuiz, error) {
	const q = `SELECT * FROM micro_quizzes WHERE job_id = $1 ORDER BY order_index, id`
	rows, err := r.db.QueryContext(ctx, q, jobID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var quizzes []models.MicroQuiz
	for rows.Next() {
		var mq models.MicroQuiz
		if err := rows.Scan(
			&mq.ID, &mq.JobID, &mq.CourseID, &mq.SectionID, &mq.SourceContentID,
			&mq.Title, &mq.Summary, &mq.QuestionsJSON, &mq.QuestionsCount,
			&mq.OrderIndex, &mq.Status, &mq.PublishedContentID,
			&mq.NodeID, &mq.Language, &mq.CreatedBy,
			&mq.CreatedAt, &mq.UpdatedAt, &mq.PublishedAt,
		); err != nil {
			return nil, err
		}
		quizzes = append(quizzes, mq)
	}
	return quizzes, rows.Err()
}

// UpdateQuizContent updates editable fields of a micro quiz (teacher edit).
func (r *MicroQuizRepository) UpdateQuizContent(
	ctx context.Context, quizID int64,
	title string, summary string,
	questionsJSON []byte, orderIndex int,
) error {
	const q = `
	UPDATE micro_quizzes
	SET title = $2, summary = $3, questions_json = $4, order_index = $5,
	    questions_count = (SELECT jsonb_array_length($4::jsonb))
	WHERE id = $1 AND status = 'draft'`
	res, err := r.db.ExecContext(ctx, q, quizID, title, summary, questionsJSON, orderIndex)
	if err != nil {
		return err
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return fmt.Errorf("quiz %d not found or already published", quizID)
	}
	return nil
}

// MarkPublished marks a quiz as published and stores the created content ID.
func (r *MicroQuizRepository) MarkPublished(ctx context.Context, quizID int64, contentID int64) error {
	const q = `
	UPDATE micro_quizzes
	SET status = 'published', published_content_id = $2, published_at = NOW()
	WHERE id = $1`
	_, err := r.db.ExecContext(ctx, q, quizID, contentID)
	return err
}

// DeleteQuiz deletes a draft quiz.
func (r *MicroQuizRepository) DeleteQuiz(ctx context.Context, quizID int64) error {
	const q = `DELETE FROM micro_quizzes WHERE id = $1 AND status = 'draft'`
	res, err := r.db.ExecContext(ctx, q, quizID)
	if err != nil {
		return err
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return fmt.Errorf("quiz %d not found or already published", quizID)
	}
	return nil
}
