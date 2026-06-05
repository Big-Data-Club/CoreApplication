// lms-service/internal/repository/section_overview_repo.go
// Raw SQL repository for the Section Overview feature.
// Follows the same patterns as micro_lesson_repo.go and micro_quiz_repo.go.
package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"

	"example/hello/internal/dto"
)

// SectionOverviewRepository handles all DB operations for section_overview_*.
type SectionOverviewRepository struct {
	db *sql.DB
}

// NewSectionOverviewRepository creates a new SectionOverviewRepository.
func NewSectionOverviewRepository(db *sql.DB) *SectionOverviewRepository {
	return &SectionOverviewRepository{db: db}
}

// ── Jobs ──────────────────────────────────────────────────────────────────────

// CreateJob inserts a new section_overview_jobs row and returns its response DTO.
func (r *SectionOverviewRepository) CreateJob(
	ctx context.Context,
	sectionID, courseID int64,
	language string,
	questionCount int,
	createdBy int64,
) (*dto.SectionOverviewJobResponse, error) {
	query := `
		INSERT INTO section_overview_jobs (
			section_id, course_id, language, question_count, created_by
		)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING id, section_id, course_id, status, progress, stage,
		          error_msg, language, question_count, logs, created_by, created_at, updated_at
	`
	var resp dto.SectionOverviewJobResponse
	err := r.db.QueryRowContext(ctx, query,
		sectionID, courseID, language, questionCount, createdBy,
	).Scan(
		&resp.ID, &resp.SectionID, &resp.CourseID, &resp.Status, &resp.Progress, &resp.Stage,
		&resp.ErrorMsg, &resp.Language, &resp.QuestionCount, &resp.Logs, &resp.CreatedBy, &resp.CreatedAt, &resp.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("section_overview_repo.CreateJob: %w", err)
	}
	return &resp, nil
}

// UpdateJobStatus updates status/progress/stage/error_msg/logs on a job.
func (r *SectionOverviewRepository) UpdateJobStatus(
	ctx context.Context,
	jobID int64,
	status string,
	progress int,
	stage string,
	errMsg string,
	logs string,
) error {
	query := `
		UPDATE section_overview_jobs
		SET status = $2,
		    progress = $3,
		    stage = $4,
		    error_msg = $5,
		    logs = CASE WHEN $6 <> '' THEN $6 ELSE logs END,
		    updated_at = NOW()
		WHERE id = $1
	`
	_, err := r.db.ExecContext(ctx, query, jobID, status, progress, stage, errMsg, logs)
	return err
}

// GetJob retrieves a single section_overview_jobs row by primary key.
func (r *SectionOverviewRepository) GetJob(ctx context.Context, jobID int64) (*dto.SectionOverviewJobResponse, error) {
	query := `
		SELECT id, section_id, course_id, status, progress, stage,
		       error_msg, language, question_count, logs, created_by, created_at, updated_at
		FROM section_overview_jobs
		WHERE id = $1
	`
	var resp dto.SectionOverviewJobResponse
	err := r.db.QueryRowContext(ctx, query, jobID).Scan(
		&resp.ID, &resp.SectionID, &resp.CourseID, &resp.Status, &resp.Progress, &resp.Stage,
		&resp.ErrorMsg, &resp.Language, &resp.QuestionCount, &resp.Logs, &resp.CreatedBy, &resp.CreatedAt, &resp.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	return &resp, nil
}

// ListJobsBySection returns all jobs for a given section, newest first.
func (r *SectionOverviewRepository) ListJobsBySection(ctx context.Context, sectionID int64) ([]*dto.SectionOverviewJobResponse, error) {
	query := `
		SELECT id, section_id, course_id, status, progress, stage,
		       error_msg, language, question_count, logs, created_by, created_at, updated_at
		FROM section_overview_jobs
		WHERE section_id = $1
		ORDER BY created_at DESC
	`
	rows, err := r.db.QueryContext(ctx, query, sectionID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var jobs []*dto.SectionOverviewJobResponse
	for rows.Next() {
		var resp dto.SectionOverviewJobResponse
		if err := rows.Scan(
			&resp.ID, &resp.SectionID, &resp.CourseID, &resp.Status, &resp.Progress, &resp.Stage,
			&resp.ErrorMsg, &resp.Language, &resp.QuestionCount, &resp.Logs, &resp.CreatedBy, &resp.CreatedAt, &resp.UpdatedAt,
		); err != nil {
			return nil, err
		}
		jobs = append(jobs, &resp)
	}
	return jobs, rows.Err()
}

// DeleteJob deletes a job row (cascade deletes its lessons and quizzes via FK).
func (r *SectionOverviewRepository) DeleteJob(ctx context.Context, jobID int64) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM section_overview_jobs WHERE id = $1`, jobID)
	return err
}

// ── Lessons ───────────────────────────────────────────────────────────────────

// CreateLesson inserts a section_overview_lessons row. references is marshalled
// to JSON before storage.
func (r *SectionOverviewRepository) CreateLesson(
	ctx context.Context,
	jobID, sectionID, courseID, createdBy int64,
	title, summary, markdownContent string,
	references []dto.OverviewReferenceItem,
) (*dto.SectionOverviewLessonResponse, error) {
	refsJSON, err := json.Marshal(references)
	if err != nil {
		return nil, fmt.Errorf("section_overview_repo.CreateLesson marshal refs: %w", err)
	}

	query := `
		INSERT INTO section_overview_lessons (
			job_id, section_id, course_id, title, summary,
			markdown_content, references_json, created_by
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		RETURNING id, job_id, section_id, course_id, title, summary,
		          markdown_content, references_json, status,
		          published_content_id, created_by, created_at, updated_at
	`
	return r.scanLesson(r.db.QueryRowContext(ctx, query,
		jobID, sectionID, courseID, title, summary,
		markdownContent, string(refsJSON), createdBy,
	))
}

// GetLesson retrieves the lesson associated with a given job_id.
func (r *SectionOverviewRepository) GetLesson(ctx context.Context, jobID int64) (*dto.SectionOverviewLessonResponse, error) {
	query := `
		SELECT id, job_id, section_id, course_id, title, summary,
		       markdown_content, references_json, status,
		       published_content_id, created_by, created_at, updated_at
		FROM section_overview_lessons
		WHERE job_id = $1
		LIMIT 1
	`
	return r.scanLesson(r.db.QueryRowContext(ctx, query, jobID))
}

// GetLessonByID retrieves a lesson by its own primary key.
func (r *SectionOverviewRepository) GetLessonByID(ctx context.Context, lessonID int64) (*dto.SectionOverviewLessonResponse, error) {
	query := `
		SELECT id, job_id, section_id, course_id, title, summary,
		       markdown_content, references_json, status,
		       published_content_id, created_by, created_at, updated_at
		FROM section_overview_lessons
		WHERE id = $1
	`
	return r.scanLesson(r.db.QueryRowContext(ctx, query, lessonID))
}

// UpdateLesson applies patch fields to a lesson (only non-nil fields are updated).
func (r *SectionOverviewRepository) UpdateLesson(ctx context.Context, lessonID int64, req dto.UpdateOverviewLessonRequest) error {
	if req.Title == nil && req.MarkdownContent == nil && req.References == nil {
		return nil // nothing to do
	}

	// Fetch current values then override with provided patches.
	current, err := r.GetLessonByID(ctx, lessonID)
	if err != nil {
		return fmt.Errorf("section_overview_repo.UpdateLesson fetch: %w", err)
	}

	title := current.Title
	if req.Title != nil {
		title = *req.Title
	}
	md := current.MarkdownContent
	if req.MarkdownContent != nil {
		md = *req.MarkdownContent
	}
	refs := current.References
	if req.References != nil {
		refs = *req.References
	}

	refsJSON, err := json.Marshal(refs)
	if err != nil {
		return fmt.Errorf("section_overview_repo.UpdateLesson marshal refs: %w", err)
	}

	query := `
		UPDATE section_overview_lessons
		SET title = $2, markdown_content = $3, references_json = $4, updated_at = NOW()
		WHERE id = $1
	`
	_, err = r.db.ExecContext(ctx, query, lessonID, title, md, string(refsJSON))
	return err
}

// MarkLessonPublished sets status='published' and records the new content ID.
func (r *SectionOverviewRepository) MarkLessonPublished(ctx context.Context, lessonID, contentID int64) error {
	query := `
		UPDATE section_overview_lessons
		SET status = 'published', published_content_id = $2, updated_at = NOW()
		WHERE id = $1
	`
	_, err := r.db.ExecContext(ctx, query, lessonID, contentID)
	return err
}

// scanLesson reads a single section_overview_lessons row from a *sql.Row.
func (r *SectionOverviewRepository) scanLesson(row *sql.Row) (*dto.SectionOverviewLessonResponse, error) {
	var resp dto.SectionOverviewLessonResponse
	var refsRaw []byte
	err := row.Scan(
		&resp.ID, &resp.JobID, &resp.SectionID, &resp.CourseID,
		&resp.Title, &resp.Summary, &resp.MarkdownContent,
		&refsRaw, &resp.Status, &resp.PublishedContentID,
		&resp.CreatedBy, &resp.CreatedAt, &resp.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	if len(refsRaw) > 0 {
		if err := json.Unmarshal(refsRaw, &resp.References); err != nil {
			resp.References = []dto.OverviewReferenceItem{}
		}
	} else {
		resp.References = []dto.OverviewReferenceItem{}
	}
	return &resp, nil
}

// ── Quizzes ───────────────────────────────────────────────────────────────────

// CreateQuiz inserts a section_overview_quizzes row. questions and references
// are marshalled to JSON before storage.
func (r *SectionOverviewRepository) CreateQuiz(
	ctx context.Context,
	jobID, sectionID, courseID, createdBy int64,
	title, summary string,
	questionCount int,
	questions []dto.OverviewQuestion,
	references []dto.OverviewReferenceItem,
) (*dto.SectionOverviewQuizResponse, error) {
	questionsJSON, err := json.Marshal(questions)
	if err != nil {
		return nil, fmt.Errorf("section_overview_repo.CreateQuiz marshal questions: %w", err)
	}
	refsJSON, err := json.Marshal(references)
	if err != nil {
		return nil, fmt.Errorf("section_overview_repo.CreateQuiz marshal refs: %w", err)
	}

	query := `
		INSERT INTO section_overview_quizzes (
			job_id, section_id, course_id, title, summary,
			question_count, questions_json, references_json, created_by
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		RETURNING id, job_id, section_id, course_id, title, summary,
		          question_count, questions_json, references_json, status,
		          published_quiz_id, created_by, created_at, updated_at
	`
	return r.scanQuiz(r.db.QueryRowContext(ctx, query,
		jobID, sectionID, courseID, title, summary,
		questionCount, string(questionsJSON), string(refsJSON), createdBy,
	))
}

// GetQuiz retrieves the quiz associated with a given job_id.
func (r *SectionOverviewRepository) GetQuiz(ctx context.Context, jobID int64) (*dto.SectionOverviewQuizResponse, error) {
	query := `
		SELECT id, job_id, section_id, course_id, title, summary,
		       question_count, questions_json, references_json, status,
		       published_quiz_id, created_by, created_at, updated_at
		FROM section_overview_quizzes
		WHERE job_id = $1
		LIMIT 1
	`
	return r.scanQuiz(r.db.QueryRowContext(ctx, query, jobID))
}

// GetQuizByID retrieves a quiz by its own primary key.
func (r *SectionOverviewRepository) GetQuizByID(ctx context.Context, quizID int64) (*dto.SectionOverviewQuizResponse, error) {
	query := `
		SELECT id, job_id, section_id, course_id, title, summary,
		       question_count, questions_json, references_json, status,
		       published_quiz_id, created_by, created_at, updated_at
		FROM section_overview_quizzes
		WHERE id = $1
	`
	return r.scanQuiz(r.db.QueryRowContext(ctx, query, quizID))
}

// UpdateQuiz applies patch fields to a quiz (only non-nil fields are updated).
func (r *SectionOverviewRepository) UpdateQuiz(ctx context.Context, quizID int64, req dto.UpdateOverviewQuizRequest) error {
	if req.Title == nil && req.Questions == nil {
		return nil // nothing to do
	}

	current, err := r.GetQuizByID(ctx, quizID)
	if err != nil {
		return fmt.Errorf("section_overview_repo.UpdateQuiz fetch: %w", err)
	}

	title := current.Title
	if req.Title != nil {
		title = *req.Title
	}
	questions := current.Questions
	if req.Questions != nil {
		questions = *req.Questions
	}

	questionsJSON, err := json.Marshal(questions)
	if err != nil {
		return fmt.Errorf("section_overview_repo.UpdateQuiz marshal questions: %w", err)
	}

	query := `
		UPDATE section_overview_quizzes
		SET title = $2, questions_json = $3, question_count = $4, updated_at = NOW()
		WHERE id = $1
	`
	_, err = r.db.ExecContext(ctx, query, quizID, title, string(questionsJSON), len(questions))
	return err
}

// MarkQuizPublished sets status='published' and records the published quiz ID.
func (r *SectionOverviewRepository) MarkQuizPublished(ctx context.Context, quizID, publishedQuizID int64) error {
	query := `
		UPDATE section_overview_quizzes
		SET status = 'published', published_quiz_id = $2, updated_at = NOW()
		WHERE id = $1
	`
	_, err := r.db.ExecContext(ctx, query, quizID, publishedQuizID)
	return err
}

// scanQuiz reads a single section_overview_quizzes row from a *sql.Row.
func (r *SectionOverviewRepository) scanQuiz(row *sql.Row) (*dto.SectionOverviewQuizResponse, error) {
	var resp dto.SectionOverviewQuizResponse
	var questionsRaw, refsRaw []byte
	err := row.Scan(
		&resp.ID, &resp.JobID, &resp.SectionID, &resp.CourseID,
		&resp.Title, &resp.Summary, &resp.QuestionCount,
		&questionsRaw, &refsRaw, &resp.Status,
		&resp.PublishedQuizID, &resp.CreatedBy, &resp.CreatedAt, &resp.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	if len(questionsRaw) > 0 {
		if err := json.Unmarshal(questionsRaw, &resp.Questions); err != nil {
			resp.Questions = []dto.OverviewQuestion{}
		}
	} else {
		resp.Questions = []dto.OverviewQuestion{}
	}
	if len(refsRaw) > 0 {
		if err := json.Unmarshal(refsRaw, &resp.References); err != nil {
			resp.References = []dto.OverviewReferenceItem{}
		}
	} else {
		resp.References = []dto.OverviewReferenceItem{}
	}
	return &resp, nil
}
