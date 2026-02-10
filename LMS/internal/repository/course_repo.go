package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"example/hello/internal/models"
)

type CourseRepository struct {
	db *sql.DB
}

func NewCourseRepository(db *sql.DB) *CourseRepository {
	return &CourseRepository{db: db}
}

// Create creates a new course
func (r *CourseRepository) Create(ctx context.Context, course *models.Course) (*models.Course, error) {
	query := `
		INSERT INTO courses (title, description, category, level, thumbnail_url, status, created_by)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
		RETURNING id, created_at, updated_at
	`

	err := r.db.QueryRowContext(ctx, query,
		course.Title,
		course.Description,
		course.Category,
		course.Level,
		course.ThumbnailURL,
		course.Status,
		course.CreatedBy,
	).Scan(&course.ID, &course.CreatedAt, &course.UpdatedAt)

	if err != nil {
		return nil, err
	}

	return course, nil
}

// GetByID retrieves a course by ID with creator info
func (r *CourseRepository) GetByID(ctx context.Context, id int64) (*models.CourseWithCreator, error) {
	query := `
		SELECT c.id, c.title, c.description, c.category, c.level, c.thumbnail_url, 
		       c.status, c.created_by, c.created_at, c.updated_at, c.published_at,
		       u.full_name as creator_name, u.email as creator_email
		FROM courses c
		LEFT JOIN users u ON c.created_by = u.id
		WHERE c.id = $1
	`

	var course models.CourseWithCreator
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&course.ID,
		&course.Title,
		&course.Description,
		&course.Category,
		&course.Level,
		&course.ThumbnailURL,
		&course.Status,
		&course.CreatedBy,
		&course.CreatedAt,
		&course.UpdatedAt,
		&course.PublishedAt,
		&course.CreatorName,
		&course.CreatorEmail,
	)

	if err != nil {
		return nil, err
	}

	return &course, nil
}

// Update updates a course
func (r *CourseRepository) Update(ctx context.Context, id int64, updates map[string]interface{}) error {
	if len(updates) == 0 {
		return fmt.Errorf("no fields to update")
	}

	query := "UPDATE courses SET "
	args := []interface{}{}
	argCount := 1

	for field, value := range updates {
		if argCount > 1 {
			query += ", "
		}
		query += fmt.Sprintf("%s = $%d", field, argCount)
		args = append(args, value)
		argCount++
	}

	query += fmt.Sprintf(" WHERE id = $%d", argCount)
	args = append(args, id)

	result, err := r.db.ExecContext(ctx, query, args...)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}

	if rows == 0 {
		return sql.ErrNoRows
	}

	return nil
}

// Delete deletes a course
func (r *CourseRepository) Delete(ctx context.Context, id int64) error {
	query := `DELETE FROM courses WHERE id = $1`

	result, err := r.db.ExecContext(ctx, query, id)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}

	if rows == 0 {
		return sql.ErrNoRows
	}

	return nil
}

// Publish publishes a course
func (r *CourseRepository) Publish(ctx context.Context, id int64) error {
	query := `
		UPDATE courses 
		SET status = $1, published_at = $2
		WHERE id = $3 AND status = $4
	`

	result, err := r.db.ExecContext(ctx, query,
		models.CourseStatusPublished,
		time.Now(),
		id,
		models.CourseStatusDraft,
	)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}

	if rows == 0 {
		return fmt.Errorf("course not found or already published")
	}

	return nil
}

// ListByCreator lists all courses created by a user
func (r *CourseRepository) ListByCreator(ctx context.Context, creatorID int64) ([]*models.CourseWithCreator, error) {
	query := `
		SELECT c.id, c.title, c.description, c.category, c.level, c.thumbnail_url,
		       c.status, c.created_by, c.created_at, c.updated_at, c.published_at,
		       u.full_name as creator_name, u.email as creator_email
		FROM courses c
		LEFT JOIN users u ON c.created_by = u.id
		WHERE c.created_by = $1
		ORDER BY c.created_at DESC
	`

	rows, err := r.db.QueryContext(ctx, query, creatorID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var courses []*models.CourseWithCreator
	for rows.Next() {
		var course models.CourseWithCreator
		err := rows.Scan(
			&course.ID,
			&course.Title,
			&course.Description,
			&course.Category,
			&course.Level,
			&course.ThumbnailURL,
			&course.Status,
			&course.CreatedBy,
			&course.CreatedAt,
			&course.UpdatedAt,
			&course.PublishedAt,
			&course.CreatorName,
			&course.CreatorEmail,
		)
		if err != nil {
			return nil, err
		}
		courses = append(courses, &course)
	}

	return courses, rows.Err()
}

// ListPublished lists all published courses
func (r *CourseRepository) ListPublished(ctx context.Context) ([]*models.CourseWithCreator, error) {
	query := `
		SELECT c.id, c.title, c.description, c.category, c.level, c.thumbnail_url,
		       c.status, c.created_by, c.created_at, c.updated_at, c.published_at,
		       u.full_name as creator_name, u.email as creator_email
		FROM courses c
		LEFT JOIN users u ON c.created_by = u.id
		WHERE c.status = $1
		ORDER BY c.published_at DESC
	`

	rows, err := r.db.QueryContext(ctx, query, models.CourseStatusPublished)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var courses []*models.CourseWithCreator
	for rows.Next() {
		var course models.CourseWithCreator
		err := rows.Scan(
			&course.ID,
			&course.Title,
			&course.Description,
			&course.Category,
			&course.Level,
			&course.ThumbnailURL,
			&course.Status,
			&course.CreatedBy,
			&course.CreatedAt,
			&course.UpdatedAt,
			&course.PublishedAt,
			&course.CreatorName,
			&course.CreatorEmail,
		)
		if err != nil {
			return nil, err
		}
		courses = append(courses, &course)
	}

	return courses, rows.Err()
}

// ===== SECTION METHODS =====

// CreateSection creates a new section
func (r *CourseRepository) CreateSection(ctx context.Context, section *models.CourseSection) (*models.CourseSection, error) {
	query := `
		INSERT INTO course_sections (course_id, title, description, order_index, is_published)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING id, created_at, updated_at
	`

	err := r.db.QueryRowContext(ctx, query,
		section.CourseID,
		section.Title,
		section.Description,
		section.OrderIndex,
		section.IsPublished,
	).Scan(&section.ID, &section.CreatedAt, &section.UpdatedAt)

	if err != nil {
		return nil, err
	}

	return section, nil
}

// GetSectionByID retrieves a section by ID
func (r *CourseRepository) GetSectionByID(ctx context.Context, id int64) (*models.CourseSection, error) {
	query := `
		SELECT id, course_id, title, description, order_index, is_published, created_at, updated_at
		FROM course_sections
		WHERE id = $1
	`

	var section models.CourseSection
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&section.ID,
		&section.CourseID,
		&section.Title,
		&section.Description,
		&section.OrderIndex,
		&section.IsPublished,
		&section.CreatedAt,
		&section.UpdatedAt,
	)

	if err != nil {
		return nil, err
	}

	return &section, nil
}

// ListSectionsByCourse lists all sections for a course
func (r *CourseRepository) ListSectionsByCourse(ctx context.Context, courseID int64) ([]*models.CourseSection, error) {
	query := `
		SELECT id, course_id, title, description, order_index, is_published, created_at, updated_at
		FROM course_sections
		WHERE course_id = $1
		ORDER BY order_index ASC
	`

	rows, err := r.db.QueryContext(ctx, query, courseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var sections []*models.CourseSection
	for rows.Next() {
		var section models.CourseSection
		err := rows.Scan(
			&section.ID,
			&section.CourseID,
			&section.Title,
			&section.Description,
			&section.OrderIndex,
			&section.IsPublished,
			&section.CreatedAt,
			&section.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}
		sections = append(sections, &section)
	}

	return sections, rows.Err()
}

// UpdateSection updates a section
func (r *CourseRepository) UpdateSection(ctx context.Context, id int64, updates map[string]interface{}) error {
	if len(updates) == 0 {
		return fmt.Errorf("no fields to update")
	}

	query := "UPDATE course_sections SET "
	args := []interface{}{}
	argCount := 1

	for field, value := range updates {
		if argCount > 1 {
			query += ", "
		}
		query += fmt.Sprintf("%s = $%d", field, argCount)
		args = append(args, value)
		argCount++
	}

	query += fmt.Sprintf(" WHERE id = $%d", argCount)
	args = append(args, id)

	result, err := r.db.ExecContext(ctx, query, args...)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}

	if rows == 0 {
		return sql.ErrNoRows
	}

	return nil
}

// DeleteSection deletes a section
func (r *CourseRepository) DeleteSection(ctx context.Context, id int64) error {
	query := `DELETE FROM course_sections WHERE id = $1`

	result, err := r.db.ExecContext(ctx, query, id)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}

	if rows == 0 {
		return sql.ErrNoRows
	}

	return nil
}

// ===== CONTENT METHODS =====

// CreateContent creates new section content
func (r *CourseRepository) CreateContent(ctx context.Context, content *models.SectionContent) (*models.SectionContent, error) {
	query := `
		INSERT INTO section_content (section_id, type, title, description, order_index, metadata, 
		                             is_published, is_mandatory, created_by)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		RETURNING id, created_at, updated_at
	`

	err := r.db.QueryRowContext(ctx, query,
		content.SectionID,
		content.Type,
		content.Title,
		content.Description,
		content.OrderIndex,
		content.Metadata,
		content.IsPublished,
		content.IsMandatory,
		content.CreatedBy,
	).Scan(&content.ID, &content.CreatedAt, &content.UpdatedAt)

	if err != nil {
		return nil, err
	}

	return content, nil
}

// GetContentByID retrieves content by ID
func (r *CourseRepository) GetContentByID(ctx context.Context, id int64) (*models.SectionContent, error) {
	query := `
		SELECT id, section_id, type, title, description, order_index, metadata,
		       is_published, is_mandatory, file_path, file_size, file_type,
		       created_by, created_at, updated_at
		FROM section_content
		WHERE id = $1
	`

	var content models.SectionContent
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&content.ID,
		&content.SectionID,
		&content.Type,
		&content.Title,
		&content.Description,
		&content.OrderIndex,
		&content.Metadata,
		&content.IsPublished,
		&content.IsMandatory,
		&content.FilePath,
		&content.FileSize,
		&content.FileType,
		&content.CreatedBy,
		&content.CreatedAt,
		&content.UpdatedAt,
	)

	if err != nil {
		return nil, err
	}

	return &content, nil
}

// ListContentBySection lists all content for a section
func (r *CourseRepository) ListContentBySection(ctx context.Context, sectionID int64) ([]*models.SectionContent, error) {
	query := `
		SELECT id, section_id, type, title, description, order_index, metadata,
		       is_published, is_mandatory, file_path, file_size, file_type,
		       created_by, created_at, updated_at
		FROM section_content
		WHERE section_id = $1
		ORDER BY order_index ASC
	`

	rows, err := r.db.QueryContext(ctx, query, sectionID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var contents []*models.SectionContent
	for rows.Next() {
		var content models.SectionContent
		err := rows.Scan(
			&content.ID,
			&content.SectionID,
			&content.Type,
			&content.Title,
			&content.Description,
			&content.OrderIndex,
			&content.Metadata,
			&content.IsPublished,
			&content.IsMandatory,
			&content.FilePath,
			&content.FileSize,
			&content.FileType,
			&content.CreatedBy,
			&content.CreatedAt,
			&content.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}
		contents = append(contents, &content)
	}

	return contents, rows.Err()
}

// UpdateContent updates section content
func (r *CourseRepository) UpdateContent(ctx context.Context, id int64, updates map[string]interface{}) error {
	if len(updates) == 0 {
		return fmt.Errorf("no fields to update")
	}

	query := "UPDATE section_content SET "
	args := []interface{}{}
	argCount := 1

	for field, value := range updates {
		if argCount > 1 {
			query += ", "
		}
		query += fmt.Sprintf("%s = $%d", field, argCount)
		args = append(args, value)
		argCount++
	}

	query += fmt.Sprintf(" WHERE id = $%d", argCount)
	args = append(args, id)

	result, err := r.db.ExecContext(ctx, query, args...)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}

	if rows == 0 {
		return sql.ErrNoRows
	}

	return nil
}

// DeleteContent deletes section content
func (r *CourseRepository) DeleteContent(ctx context.Context, id int64) error {
	query := `DELETE FROM section_content WHERE id = $1`

	result, err := r.db.ExecContext(ctx, query, id)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}

	if rows == 0 {
		return sql.ErrNoRows
	}

	return nil
}

// Helper function to convert metadata to JSON
func metadataToJSON(metadata map[string]interface{}) ([]byte, error) {
	if metadata == nil {
		return json.Marshal(map[string]interface{}{})
	}
	return json.Marshal(metadata)
}