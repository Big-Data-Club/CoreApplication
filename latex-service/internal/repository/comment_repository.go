package repository

import (
	"context"
	"database/sql"
	"errors"
	"time"

	"latex-service/internal/dto"
)

// CommentRepository handles persistence for project comments
type CommentRepository struct {
	db *sql.DB
}

// NewCommentRepository creates a new CommentRepository
func NewCommentRepository(db *sql.DB) *CommentRepository {
	return &CommentRepository{db: db}
}

// Create inserts a new comment and returns the created record
func (r *CommentRepository) Create(ctx context.Context, projectID, fileID, userID int64, email, content string, selStart, selEnd *int, selText *string, parentID *int64) (*dto.CommentResponse, error) {
	var resp dto.CommentResponse
	query := `
		INSERT INTO latex_comments
			(project_id, file_id, user_id, user_email, content, selection_start, selection_end, selected_text, parent_id)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		RETURNING id, project_id, file_id, user_id, user_email, content,
		          selection_start, selection_end, selected_text, parent_id,
		          resolved, resolved_by, resolved_at, created_at, updated_at
	`
	row := r.db.QueryRowContext(ctx, query,
		projectID, fileID, userID, email, content,
		selStart, selEnd, selText, parentID,
	)
	return scanComment(row, &resp)
}

// GetByID retrieves a comment by its primary key
func (r *CommentRepository) GetByID(ctx context.Context, id int64) (*dto.CommentResponse, error) {
	var resp dto.CommentResponse
	query := `
		SELECT id, project_id, file_id, user_id, user_email, content,
		       selection_start, selection_end, selected_text, parent_id,
		       resolved, resolved_by, resolved_at, created_at, updated_at
		FROM latex_comments WHERE id = $1
	`
	row := r.db.QueryRowContext(ctx, query, id)
	c, err := scanComment(row, &resp)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, errors.New("comment not found")
		}
		return nil, err
	}
	return c, nil
}

// ListByFile returns all top-level comments for a file, with replies nested
func (r *CommentRepository) ListByFile(ctx context.Context, fileID int64) ([]*dto.CommentResponse, error) {
	return r.listComments(ctx, `WHERE file_id = $1`, fileID)
}

// ListByProject returns all top-level comments for a project, with replies nested
func (r *CommentRepository) ListByProject(ctx context.Context, projectID int64) ([]*dto.CommentResponse, error) {
	return r.listComments(ctx, `WHERE project_id = $1`, projectID)
}

func (r *CommentRepository) listComments(ctx context.Context, whereClause string, arg int64) ([]*dto.CommentResponse, error) {
	query := `
		SELECT id, project_id, file_id, user_id, user_email, content,
		       selection_start, selection_end, selected_text, parent_id,
		       resolved, resolved_by, resolved_at, created_at, updated_at
		FROM latex_comments ` + whereClause + `
		ORDER BY created_at ASC
	`
	rows, err := r.db.QueryContext(ctx, query, arg)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	all := make(map[int64]*dto.CommentResponse)
	var ordered []int64

	for rows.Next() {
		var c dto.CommentResponse
		if err := scanCommentRow(rows, &c); err != nil {
			return nil, err
		}
		all[c.ID] = &c
		ordered = append(ordered, c.ID)
	}

	// Build thread tree
	var roots []*dto.CommentResponse
	for _, id := range ordered {
		c := all[id]
		if c.ParentID == nil {
			roots = append(roots, c)
		} else {
			parent, ok := all[*c.ParentID]
			if ok {
				parent.Replies = append(parent.Replies, c)
			} else {
				roots = append(roots, c) // orphaned reply — show at top level
			}
		}
	}
	return roots, nil
}

// Update edits the content of a comment
func (r *CommentRepository) Update(ctx context.Context, id int64, content string) (*dto.CommentResponse, error) {
	var resp dto.CommentResponse
	query := `
		UPDATE latex_comments SET content = $1, updated_at = NOW()
		WHERE id = $2
		RETURNING id, project_id, file_id, user_id, user_email, content,
		          selection_start, selection_end, selected_text, parent_id,
		          resolved, resolved_by, resolved_at, created_at, updated_at
	`
	row := r.db.QueryRowContext(ctx, query, content, id)
	return scanComment(row, &resp)
}

// Resolve marks a comment as resolved
func (r *CommentRepository) Resolve(ctx context.Context, id, resolvedBy int64) error {
	now := time.Now()
	res, err := r.db.ExecContext(ctx,
		`UPDATE latex_comments SET resolved = TRUE, resolved_by = $1, resolved_at = $2, updated_at = NOW() WHERE id = $3`,
		resolvedBy, now, id,
	)
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		return errors.New("comment not found")
	}
	return nil
}

// Unresolve reopens a resolved comment
func (r *CommentRepository) Unresolve(ctx context.Context, id int64) error {
	res, err := r.db.ExecContext(ctx,
		`UPDATE latex_comments SET resolved = FALSE, resolved_by = NULL, resolved_at = NULL, updated_at = NOW() WHERE id = $1`,
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
		return errors.New("comment not found")
	}
	return nil
}

// Delete removes a comment and its replies (via CASCADE)
func (r *CommentRepository) Delete(ctx context.Context, id int64) error {
	res, err := r.db.ExecContext(ctx, `DELETE FROM latex_comments WHERE id = $1`, id)
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		return errors.New("comment not found")
	}
	return nil
}

// ── scan helpers ────────────────────────────────────────────────────────────

type rowScanner interface {
	Scan(dest ...interface{}) error
}

func scanComment(row rowScanner, c *dto.CommentResponse) (*dto.CommentResponse, error) {
	err := row.Scan(
		&c.ID, &c.ProjectID, &c.FileID, &c.UserID, &c.UserEmail, &c.Content,
		&c.SelectionStart, &c.SelectionEnd, &c.SelectedText, &c.ParentID,
		&c.Resolved, &c.ResolvedBy, &c.ResolvedAt, &c.CreatedAt, &c.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	return c, nil
}

func scanCommentRow(rows *sql.Rows, c *dto.CommentResponse) error {
	return rows.Scan(
		&c.ID, &c.ProjectID, &c.FileID, &c.UserID, &c.UserEmail, &c.Content,
		&c.SelectionStart, &c.SelectionEnd, &c.SelectedText, &c.ParentID,
		&c.Resolved, &c.ResolvedBy, &c.ResolvedAt, &c.CreatedAt, &c.UpdatedAt,
	)
}
