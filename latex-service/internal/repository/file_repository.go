package repository

import (
	"context"
	"database/sql"
	"errors"

	"latex-service/internal/dto"
)

type FileRepository struct {
	db *sql.DB
}

func NewFileRepository(db *sql.DB) *FileRepository {
	return &FileRepository{db: db}
}

// Create inserts a new file metadata record
func (r *FileRepository) Create(ctx context.Context, projectID int64, filename, filepath string, size int64, mimeType string, hash string) (*dto.FileResponse, error) {
	var resp dto.FileResponse
	query := `
		INSERT INTO latex_project_files (project_id, filename, filepath, file_size, mime_type, content_hash)
		VALUES ($1, $2, $3, $4, $5, $6)
		ON CONFLICT (project_id, filename) DO UPDATE
		SET filepath = EXCLUDED.filepath, file_size = EXCLUDED.file_size, mime_type = EXCLUDED.mime_type, content_hash = EXCLUDED.content_hash, updated_at = NOW()
		RETURNING id, project_id, filename, filepath, file_size, mime_type, content_hash, created_at, updated_at
	`
	err := r.db.QueryRowContext(ctx, query, projectID, filename, filepath, size, mimeType, hash).Scan(
		&resp.ID, &resp.ProjectID, &resp.Filename, &resp.Filepath, &resp.FileSize, &resp.MimeType, &resp.ContentHash, &resp.CreatedAt, &resp.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	return &resp, nil
}

// GetByID retrieves a file by ID
func (r *FileRepository) GetByID(ctx context.Context, id int64) (*dto.FileResponse, error) {
	var resp dto.FileResponse
	query := `
		SELECT id, project_id, filename, filepath, file_size, mime_type, content_hash, created_at, updated_at
		FROM latex_project_files
		WHERE id = $1
	`
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&resp.ID, &resp.ProjectID, &resp.Filename, &resp.Filepath, &resp.FileSize, &resp.MimeType, &resp.ContentHash, &resp.CreatedAt, &resp.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, errors.New("file not found")
		}
		return nil, err
	}
	return &resp, nil
}

// GetByFilename retrieves file metadata by project ID and filename
func (r *FileRepository) GetByFilename(ctx context.Context, projectID int64, filename string) (*dto.FileResponse, error) {
	var resp dto.FileResponse
	query := `
		SELECT id, project_id, filename, filepath, file_size, mime_type, content_hash, created_at, updated_at
		FROM latex_project_files
		WHERE project_id = $1 AND filename = $2
	`
	err := r.db.QueryRowContext(ctx, query, projectID, filename).Scan(
		&resp.ID, &resp.ProjectID, &resp.Filename, &resp.Filepath, &resp.FileSize, &resp.MimeType, &resp.ContentHash, &resp.CreatedAt, &resp.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, errors.New("file not found")
		}
		return nil, err
	}
	return &resp, nil
}

// ListByProject lists all files in a project
func (r *FileRepository) ListByProject(ctx context.Context, projectID int64) ([]*dto.FileResponse, error) {
	query := `
		SELECT id, project_id, filename, filepath, file_size, mime_type, content_hash, created_at, updated_at
		FROM latex_project_files
		WHERE project_id = $1
		ORDER BY filename ASC
	`
	rows, err := r.db.QueryContext(ctx, query, projectID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var files []*dto.FileResponse
	for rows.Next() {
		var f dto.FileResponse
		err := rows.Scan(
			&f.ID, &f.ProjectID, &f.Filename, &f.Filepath, &f.FileSize, &f.MimeType, &f.ContentHash, &f.CreatedAt, &f.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}
		files = append(files, &f)
	}
	return files, nil
}

// UpdateMetadata updates file size and content hash
func (r *FileRepository) UpdateMetadata(ctx context.Context, id int64, size int64, hash string) error {
	query := `
		UPDATE latex_project_files
		SET file_size = $1, content_hash = $2, updated_at = NOW()
		WHERE id = $3
	`
	res, err := r.db.ExecContext(ctx, query, size, hash, id)
	if err != nil {
		return err
	}
	rows, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if rows == 0 {
		return errors.New("file not found")
	}
	return nil
}

// Delete removes a file record from database
func (r *FileRepository) Delete(ctx context.Context, id int64) error {
	query := `
		DELETE FROM latex_project_files
		WHERE id = $1
	`
	res, err := r.db.ExecContext(ctx, query, id)
	if err != nil {
		return err
	}
	rows, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if rows == 0 {
		return errors.New("file not found")
	}
	return nil
}

// UpdateFilename updates a file's name
func (r *FileRepository) UpdateFilename(ctx context.Context, id int64, filename string) error {
	query := `
		UPDATE latex_project_files
		SET filename = $1, updated_at = NOW()
		WHERE id = $2
	`
	res, err := r.db.ExecContext(ctx, query, filename, id)
	if err != nil {
		return err
	}
	rows, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if rows == 0 {
		return errors.New("file not found")
	}
	return nil
}
