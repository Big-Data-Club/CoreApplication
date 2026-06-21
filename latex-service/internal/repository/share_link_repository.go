package repository

import (
	"context"
	"database/sql"
	"errors"
	"time"

	"latex-service/internal/dto"
)

// ShareLinkRepository handles persistence for project share links
type ShareLinkRepository struct {
	db *sql.DB
}

// NewShareLinkRepository creates a new ShareLinkRepository
func NewShareLinkRepository(db *sql.DB) *ShareLinkRepository {
	return &ShareLinkRepository{db: db}
}

// Create inserts a new share link record
func (r *ShareLinkRepository) Create(ctx context.Context, projectID int64, token, role string, createdBy int64, expiresAt *time.Time) (*dto.ShareLinkResponse, error) {
	var resp dto.ShareLinkResponse
	query := `
		INSERT INTO latex_share_links (project_id, token, role, created_by, expires_at)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING id, project_id, token, role, created_by, active, expires_at, created_at
	`
	err := r.db.QueryRowContext(ctx, query, projectID, token, role, createdBy, expiresAt).Scan(
		&resp.ID, &resp.ProjectID, &resp.Token, &resp.Role, &resp.CreatedBy, &resp.Active, &resp.ExpiresAt, &resp.CreatedAt,
	)
	if err != nil {
		return nil, err
	}
	return &resp, nil
}

// GetByToken retrieves an active share link by its token
func (r *ShareLinkRepository) GetByToken(ctx context.Context, token string) (*dto.ShareLinkResponse, error) {
	var resp dto.ShareLinkResponse
	query := `
		SELECT id, project_id, token, role, created_by, active, expires_at, created_at
		FROM latex_share_links
		WHERE token = $1 AND active = TRUE
	`
	err := r.db.QueryRowContext(ctx, query, token).Scan(
		&resp.ID, &resp.ProjectID, &resp.Token, &resp.Role, &resp.CreatedBy, &resp.Active, &resp.ExpiresAt, &resp.CreatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, errors.New("share link not found or inactive")
		}
		return nil, err
	}
	return &resp, nil
}

// ListByProject returns all share links for a project
func (r *ShareLinkRepository) ListByProject(ctx context.Context, projectID int64) ([]*dto.ShareLinkResponse, error) {
	query := `
		SELECT id, project_id, token, role, created_by, active, expires_at, created_at
		FROM latex_share_links
		WHERE project_id = $1
		ORDER BY created_at DESC
	`
	rows, err := r.db.QueryContext(ctx, query, projectID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var links []*dto.ShareLinkResponse
	for rows.Next() {
		var l dto.ShareLinkResponse
		if err := rows.Scan(
			&l.ID, &l.ProjectID, &l.Token, &l.Role, &l.CreatedBy, &l.Active, &l.ExpiresAt, &l.CreatedAt,
		); err != nil {
			return nil, err
		}
		links = append(links, &l)
	}
	return links, nil
}

// Deactivate marks a share link as inactive without deleting it
func (r *ShareLinkRepository) Deactivate(ctx context.Context, id int64) error {
	res, err := r.db.ExecContext(ctx,
		`UPDATE latex_share_links SET active = FALSE WHERE id = $1`,
		id,
	)
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		return errors.New("share link not found")
	}
	return nil
}
