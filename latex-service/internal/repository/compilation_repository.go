package repository

import (
	"context"
	"database/sql"
	"errors"

	"latex-service/internal/dto"
)

type CompilationRepository struct {
	db *sql.DB
}

func NewCompilationRepository(db *sql.DB) *CompilationRepository {
	return &CompilationRepository{db: db}
}

// Create inserts a new compilation record
func (r *CompilationRepository) Create(ctx context.Context, projectID int64, userID int64, jobID string, compiler string) (*dto.CompileStatusResponse, error) {
	var resp dto.CompileStatusResponse
	query := `
		INSERT INTO latex_compilations (project_id, user_id, job_id, compiler, status)
		VALUES ($1, $2, $3, $4, 'queued')
		RETURNING job_id, project_id, user_id, compiler, status, created_at
	`
	err := r.db.QueryRowContext(ctx, query, projectID, userID, jobID, compiler).Scan(
		&resp.JobID, &resp.ProjectID, &resp.UserID, &resp.Compiler, &resp.Status, &resp.CreatedAt,
	)
	if err != nil {
		return nil, err
	}
	return &resp, nil
}

// Update updates a compilation record with status and outputs
func (r *CompilationRepository) Update(ctx context.Context, jobID string, status string, pdfPath *string, logOutput *string, errMsg *string, durationMs int) error {
	query := `
		UPDATE latex_compilations
		SET status = $1, pdf_path = $2, log_output = $3, error_message = $4, duration_ms = $5, completed_at = NOW()
		WHERE job_id = $6
	`
	var pdf, logOut, errStr sql.NullString
	if pdfPath != nil {
		pdf = sql.NullString{String: *pdfPath, Valid: true}
	}
	if logOutput != nil {
		logOut = sql.NullString{String: *logOutput, Valid: true}
	}
	if errMsg != nil {
		errStr = sql.NullString{String: *errMsg, Valid: true}
	}

	res, err := r.db.ExecContext(ctx, query, status, pdf, logOut, errStr, durationMs, jobID)
	if err != nil {
		return err
	}

	rows, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if rows == 0 {
		return errors.New("compilation job not found")
	}
	return nil
}

// GetByJobID retrieves compilation details by job UUID
func (r *CompilationRepository) GetByJobID(ctx context.Context, jobID string) (*dto.CompileStatusResponse, error) {
	var resp dto.CompileStatusResponse
	query := `
		SELECT job_id, project_id, user_id, compiler, status, pdf_path, log_output, error_message, duration_ms, created_at, completed_at
		FROM latex_compilations
		WHERE job_id = $1
	`
	var pdf, logOut, errStr sql.NullString
	var duration sql.NullInt32
	var completedAt sql.NullTime

	err := r.db.QueryRowContext(ctx, query, jobID).Scan(
		&resp.JobID, &resp.ProjectID, &resp.UserID, &resp.Compiler, &resp.Status, &pdf, &logOut, &errStr, &duration, &resp.CreatedAt, &completedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, errors.New("compilation job not found")
		}
		return nil, err
	}

	if pdf.Valid {
		resp.PdfPath = &pdf.String
	}
	if logOut.Valid {
		resp.LogOutput = &logOut.String
	}
	if errStr.Valid {
		resp.ErrorMessage = &errStr.String
	}
	if duration.Valid {
		dVal := int(duration.Int32)
		resp.DurationMs = &dVal
	}
	if completedAt.Valid {
		resp.CompletedAt = &completedAt.Time
	}

	return &resp, nil
}

// ListByProjectID lists compilations for a project
func (r *CompilationRepository) ListByProjectID(ctx context.Context, projectID int64, limit, offset int) ([]*dto.CompileStatusResponse, error) {
	query := `
		SELECT job_id, project_id, user_id, compiler, status, pdf_path, log_output, error_message, duration_ms, created_at, completed_at
		FROM latex_compilations
		WHERE project_id = $1
		ORDER BY created_at DESC
		LIMIT $2 OFFSET $3
	`
	rows, err := r.db.QueryContext(ctx, query, projectID, limit, offset)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var compilations []*dto.CompileStatusResponse
	for rows.Next() {
		var c dto.CompileStatusResponse
		var pdf, logOut, errStr sql.NullString
		var duration sql.NullInt32
		var completedAt sql.NullTime

		err := rows.Scan(
			&c.JobID, &c.ProjectID, &c.UserID, &c.Compiler, &c.Status, &pdf, &logOut, &errStr, &duration, &c.CreatedAt, &completedAt,
		)
		if err != nil {
			return nil, err
		}

		if pdf.Valid {
			c.PdfPath = &pdf.String
		}
		if logOut.Valid {
			c.LogOutput = &logOut.String
		}
		if errStr.Valid {
			c.ErrorMessage = &errStr.String
		}
		if duration.Valid {
			dVal := int(duration.Int32)
			c.DurationMs = &dVal
		}
		if completedAt.Valid {
			c.CompletedAt = &completedAt.Time
		}

		compilations = append(compilations, &c)
	}

	return compilations, nil
}
