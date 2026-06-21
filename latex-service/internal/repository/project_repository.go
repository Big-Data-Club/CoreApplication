package repository

import (
	"context"
	"database/sql"
	"errors"

	"latex-service/internal/dto"
)

type ProjectRepository struct {
	db *sql.DB
}

func NewProjectRepository(db *sql.DB) *ProjectRepository {
	return &ProjectRepository{db: db}
}

// Create inserts a new LaTeX project
func (r *ProjectRepository) Create(ctx context.Context, req *dto.CreateProjectRequest, userID int64) (*dto.ProjectResponse, error) {
	var resp dto.ProjectResponse
	query := `
		INSERT INTO latex_projects (user_id, title, description, compiler, template_id, status)
		VALUES ($1, $2, $3, $4, $5, 'active')
		RETURNING id, user_id, title, description, compiler, main_file, template_id, status, created_at, updated_at
	`
	compiler := req.Compiler
	if compiler == "" {
		compiler = "pdflatex"
	}

	var tempID sql.NullString
	if req.TemplateID != "" {
		tempID = sql.NullString{String: req.TemplateID, Valid: true}
	}

	err := r.db.QueryRowContext(ctx, query, userID, req.Title, req.Description, compiler, tempID).Scan(
		&resp.ID, &resp.UserID, &resp.Title, &resp.Description, &resp.Compiler, &resp.MainFile, &tempID, &resp.Status, &resp.CreatedAt, &resp.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}

	if tempID.Valid {
		resp.TemplateID = &tempID.String
	}

	return &resp, nil
}

// GetByID retrieves a project by ID and verifies user ownership
func (r *ProjectRepository) GetByID(ctx context.Context, id int64, userID int64) (*dto.ProjectResponse, error) {
	var resp dto.ProjectResponse
	query := `
		SELECT id, user_id, title, description, compiler, main_file, template_id, status, created_at, updated_at
		FROM latex_projects
		WHERE id = $1 AND user_id = $2 AND status = 'active'
	`
	var tempID sql.NullString
	err := r.db.QueryRowContext(ctx, query, id, userID).Scan(
		&resp.ID, &resp.UserID, &resp.Title, &resp.Description, &resp.Compiler, &resp.MainFile, &tempID, &resp.Status, &resp.CreatedAt, &resp.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, errors.New("project not found")
		}
		return nil, err
	}

	if tempID.Valid {
		resp.TemplateID = &tempID.String
	}

	return &resp, nil
}

// ListByUserID lists a user's active projects with pagination
func (r *ProjectRepository) ListByUserID(ctx context.Context, userID int64, limit, offset int) ([]*dto.ProjectResponse, int, error) {
	countQuery := `
		SELECT COUNT(*) FROM latex_projects WHERE user_id = $1 AND status = 'active'
	`
	var total int
	err := r.db.QueryRowContext(ctx, countQuery, userID).Scan(&total)
	if err != nil {
		return nil, 0, err
	}

	query := `
		SELECT id, user_id, title, description, compiler, main_file, template_id, status, created_at, updated_at
		FROM latex_projects
		WHERE user_id = $1 AND status = 'active'
		ORDER BY updated_at DESC
		LIMIT $2 OFFSET $3
	`
	rows, err := r.db.QueryContext(ctx, query, userID, limit, offset)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	var projects []*dto.ProjectResponse
	for rows.Next() {
		var p dto.ProjectResponse
		var tempID sql.NullString
		err := rows.Scan(
			&p.ID, &p.UserID, &p.Title, &p.Description, &p.Compiler, &p.MainFile, &tempID, &p.Status, &p.CreatedAt, &p.UpdatedAt,
		)
		if err != nil {
			return nil, 0, err
		}
		if tempID.Valid {
			p.TemplateID = &tempID.String
		}
		projects = append(projects, &p)
	}

	return projects, total, nil
}

// Update updates project metadata
func (r *ProjectRepository) Update(ctx context.Context, id int64, userID int64, req *dto.UpdateProjectRequest) (*dto.ProjectResponse, error) {
	// First get current project
	curr, err := r.GetByID(ctx, id, userID)
	if err != nil {
		return nil, err
	}

	title := curr.Title
	if req.Title != nil {
		title = *req.Title
	}
	description := curr.Description
	if req.Description != nil {
		description = *req.Description
	}
	compiler := curr.Compiler
	if req.Compiler != nil {
		compiler = *req.Compiler
	}
	mainFile := curr.MainFile
	if req.MainFile != nil {
		mainFile = *req.MainFile
	}

	query := `
		UPDATE latex_projects
		SET title = $1, description = $2, compiler = $3, main_file = $4, updated_at = NOW()
		WHERE id = $5 AND user_id = $6 AND status = 'active'
		RETURNING id, user_id, title, description, compiler, main_file, template_id, status, created_at, updated_at
	`
	var resp dto.ProjectResponse
	var tempID sql.NullString
	err = r.db.QueryRowContext(ctx, query, title, description, compiler, mainFile, id, userID).Scan(
		&resp.ID, &resp.UserID, &resp.Title, &resp.Description, &resp.Compiler, &resp.MainFile, &tempID, &resp.Status, &resp.CreatedAt, &resp.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}

	if tempID.Valid {
		resp.TemplateID = &tempID.String
	}

	return &resp, nil
}

// Delete soft-deletes a project
func (r *ProjectRepository) Delete(ctx context.Context, id int64, userID int64) error {
	query := `
		UPDATE latex_projects
		SET status = 'deleted', updated_at = NOW()
		WHERE id = $1 AND user_id = $2 AND status = 'active'
	`
	res, err := r.db.ExecContext(ctx, query, id, userID)
	if err != nil {
		return err
	}

	rows, err := res.RowsAffected()
	if err != nil {
		return err
	}

	if rows == 0 {
		return errors.New("project not found or already deleted")
	}

	return nil
}
