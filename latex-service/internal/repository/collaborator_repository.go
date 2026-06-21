package repository

import (
	"context"
	"database/sql"
	"errors"

	"latex-service/internal/dto"
)

// CollaboratorRepository handles persistence for project collaborators
type CollaboratorRepository struct {
	db *sql.DB
}

// NewCollaboratorRepository creates a new CollaboratorRepository
func NewCollaboratorRepository(db *sql.DB) *CollaboratorRepository {
	return &CollaboratorRepository{db: db}
}

// Add inserts a new collaborator record. Returns error if user is already a collaborator.
func (r *CollaboratorRepository) Add(ctx context.Context, projectID, userID int64, email, role string, addedBy int64) (*dto.CollaboratorResponse, error) {
	var resp dto.CollaboratorResponse
	query := `
		INSERT INTO latex_project_collaborators (project_id, user_id, user_email, role, added_by)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING id, project_id, user_id, user_email, role, added_by, created_at
	`
	err := r.db.QueryRowContext(ctx, query, projectID, userID, email, role, addedBy).Scan(
		&resp.ID, &resp.ProjectID, &resp.UserID, &resp.UserEmail, &resp.Role, &resp.AddedBy, &resp.CreatedAt,
	)
	if err != nil {
		return nil, err
	}
	return &resp, nil
}

// GetByProjectAndUser retrieves a single collaborator record by project + user IDs
func (r *CollaboratorRepository) GetByProjectAndUser(ctx context.Context, projectID, userID int64) (*dto.CollaboratorResponse, error) {
	var resp dto.CollaboratorResponse
	query := `
		SELECT id, project_id, user_id, user_email, role, added_by, created_at
		FROM latex_project_collaborators
		WHERE project_id = $1 AND user_id = $2
	`
	err := r.db.QueryRowContext(ctx, query, projectID, userID).Scan(
		&resp.ID, &resp.ProjectID, &resp.UserID, &resp.UserEmail, &resp.Role, &resp.AddedBy, &resp.CreatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, errors.New("collaborator not found")
		}
		return nil, err
	}
	return &resp, nil
}

// ListByProject returns all collaborators for a project
func (r *CollaboratorRepository) ListByProject(ctx context.Context, projectID int64) ([]*dto.CollaboratorResponse, error) {
	query := `
		SELECT id, project_id, user_id, user_email, role, added_by, created_at
		FROM latex_project_collaborators
		WHERE project_id = $1
		ORDER BY created_at ASC
	`
	rows, err := r.db.QueryContext(ctx, query, projectID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var collabs []*dto.CollaboratorResponse
	for rows.Next() {
		var c dto.CollaboratorResponse
		if err := rows.Scan(&c.ID, &c.ProjectID, &c.UserID, &c.UserEmail, &c.Role, &c.AddedBy, &c.CreatedAt); err != nil {
			return nil, err
		}
		collabs = append(collabs, &c)
	}
	return collabs, nil
}

// UpdateRole changes the role of an existing collaborator
func (r *CollaboratorRepository) UpdateRole(ctx context.Context, projectID, userID int64, role string) (*dto.CollaboratorResponse, error) {
	var resp dto.CollaboratorResponse
	query := `
		UPDATE latex_project_collaborators
		SET role = $1, updated_at = NOW()
		WHERE project_id = $2 AND user_id = $3
		RETURNING id, project_id, user_id, user_email, role, added_by, created_at
	`
	err := r.db.QueryRowContext(ctx, query, role, projectID, userID).Scan(
		&resp.ID, &resp.ProjectID, &resp.UserID, &resp.UserEmail, &resp.Role, &resp.AddedBy, &resp.CreatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, errors.New("collaborator not found")
		}
		return nil, err
	}
	return &resp, nil
}

// Remove deletes a collaborator from a project
func (r *CollaboratorRepository) Remove(ctx context.Context, projectID, userID int64) error {
	res, err := r.db.ExecContext(ctx,
		`DELETE FROM latex_project_collaborators WHERE project_id = $1 AND user_id = $2`,
		projectID, userID,
	)
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		return errors.New("collaborator not found")
	}
	return nil
}
