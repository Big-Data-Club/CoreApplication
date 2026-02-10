package repository

import (
	"context"
	"database/sql"
	"fmt"

	"example/hello/internal/models"
)

type EnrollmentRepository struct {
	db *sql.DB
}

func NewEnrollmentRepository(db *sql.DB) *EnrollmentRepository {
	return &EnrollmentRepository{db: db}
}

// Create creates a new enrollment
func (r *EnrollmentRepository) Create(ctx context.Context, enrollment *models.Enrollment) (*models.Enrollment, error) {
	query := `
		INSERT INTO enrollments (course_id, student_id, status)
		VALUES ($1, $2, $3)
		RETURNING id, course_id, student_id, status, enrolled_at, accepted_at, rejected_at, created_at, updated_at
	`

	var result models.Enrollment
	err := r.db.QueryRowContext(ctx, query,
		enrollment.CourseID,
		enrollment.StudentID,
		enrollment.Status,
	).Scan(
		&result.ID,
		&result.CourseID,
		&result.StudentID,
		&result.Status,
		&result.EnrolledAt,
		&result.AcceptedAt,
		&result.RejectedAt,
		&result.CreatedAt,
		&result.UpdatedAt,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to create enrollment: %w", err)
	}

	return &result, nil
}

// GetByID retrieves an enrollment by ID
func (r *EnrollmentRepository) GetByID(ctx context.Context, id int64) (*models.Enrollment, error) {
	query := `
		SELECT id, course_id, student_id, status, enrolled_at, accepted_at, rejected_at, created_at, updated_at
		FROM enrollments WHERE id = $1
	`

	var enrollment models.Enrollment
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&enrollment.ID,
		&enrollment.CourseID,
		&enrollment.StudentID,
		&enrollment.Status,
		&enrollment.EnrolledAt,
		&enrollment.AcceptedAt,
		&enrollment.RejectedAt,
		&enrollment.CreatedAt,
		&enrollment.UpdatedAt,
	)

	if err != nil {
		return nil, err
	}

	return &enrollment, nil
}

// GetByStudentAndCourse checks if student is enrolled in course
func (r *EnrollmentRepository) GetByStudentAndCourse(ctx context.Context, studentID, courseID int64) (*models.Enrollment, error) {
	query := `
		SELECT id, course_id, student_id, status, enrolled_at, accepted_at, rejected_at, created_at, updated_at
		FROM enrollments WHERE student_id = $1 AND course_id = $2
	`

	var enrollment models.Enrollment
	err := r.db.QueryRowContext(ctx, query, studentID, courseID).Scan(
		&enrollment.ID,
		&enrollment.CourseID,
		&enrollment.StudentID,
		&enrollment.Status,
		&enrollment.EnrolledAt,
		&enrollment.AcceptedAt,
		&enrollment.RejectedAt,
		&enrollment.CreatedAt,
		&enrollment.UpdatedAt,
	)

	if err != nil {
		return nil, err
	}

	return &enrollment, nil
}

// ListByStudent lists all enrollments for a student
func (r *EnrollmentRepository) ListByStudent(ctx context.Context, studentID int64, status string) ([]*models.EnrollmentWithCourse, error) {
	query := `
		SELECT e.id, e.course_id, e.student_id, e.status, e.enrolled_at, e.accepted_at, e.rejected_at, e.created_at, e.updated_at,
		       c.title, u.full_name, u.email
		FROM enrollments e
		JOIN courses c ON e.course_id = c.id
		JOIN users u ON c.created_by = u.id
		WHERE e.student_id = $1
	`
	args := []interface{}{studentID}

	if status != "" {
		query += ` AND e.status = $2`
		args = append(args, status)
	}

	query += ` ORDER BY e.enrolled_at DESC`

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to list enrollments: %w", err)
	}
	defer rows.Close()

	var enrollments []*models.EnrollmentWithCourse
	for rows.Next() {
		var e models.EnrollmentWithCourse
		err := rows.Scan(
			&e.ID, &e.CourseID, &e.StudentID, &e.Status, &e.EnrolledAt, &e.AcceptedAt, &e.RejectedAt, &e.CreatedAt, &e.UpdatedAt,
			&e.CourseTitle, &e.TeacherName, &e.TeacherEmail,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan enrollment: %w", err)
		}
		enrollments = append(enrollments, &e)
	}

	return enrollments, rows.Err()
}

// ListByCourse lists all learners in a course
func (r *EnrollmentRepository) ListByCourse(ctx context.Context, courseID int64, status string) ([]*models.EnrollmentWithStudent, error) {
	query := `
		SELECT e.id, e.course_id, e.student_id, e.status, e.enrolled_at, e.accepted_at, e.rejected_at, e.created_at, e.updated_at,
		       u.full_name, u.email
		FROM enrollments e
		JOIN users u ON e.student_id = u.id
		WHERE e.course_id = $1
	`
	args := []interface{}{courseID}

	if status != "" {
		query += ` AND e.status = $2`
		args = append(args, status)
	}

	query += ` ORDER BY e.enrolled_at DESC`

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to list course learners: %w", err)
	}
	defer rows.Close()

	var enrollments []*models.EnrollmentWithStudent
	for rows.Next() {
		var e models.EnrollmentWithStudent
		err := rows.Scan(
			&e.ID, &e.CourseID, &e.StudentID, &e.Status, &e.EnrolledAt, &e.AcceptedAt, &e.RejectedAt, &e.CreatedAt, &e.UpdatedAt,
			&e.StudentName, &e.StudentEmail,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan enrollment: %w", err)
		}
		enrollments = append(enrollments, &e)
	}

	return enrollments, rows.Err()
}

// UpdateStatus updates enrollment status
func (r *EnrollmentRepository) UpdateStatus(ctx context.Context, id int64, status string) error {
	var query string
	var args []interface{}

	switch status {
	case models.EnrollmentAccepted:
		query = `UPDATE enrollments SET status = $1, accepted_at = CURRENT_TIMESTAMP WHERE id = $2`
		args = []interface{}{status, id}
	case models.EnrollmentRejected:
		query = `UPDATE enrollments SET status = $1, rejected_at = CURRENT_TIMESTAMP WHERE id = $2`
		args = []interface{}{status, id}
	default:
		return fmt.Errorf("invalid status: %s", status)
	}

	result, err := r.db.ExecContext(ctx, query, args...)
	if err != nil {
		return fmt.Errorf("failed to update enrollment status: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return sql.ErrNoRows
	}

	return nil
}

// Delete deletes an enrollment
func (r *EnrollmentRepository) Delete(ctx context.Context, id int64) error {
	query := `DELETE FROM enrollments WHERE id = $1`

	result, err := r.db.ExecContext(ctx, query, id)
	if err != nil {
		return fmt.Errorf("failed to delete enrollment: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return sql.ErrNoRows
	}

	return nil
}

// CreateBulkLog creates a bulk enrollment log
func (r *EnrollmentRepository) CreateBulkLog(ctx context.Context, log *models.BulkEnrollmentLog) (*models.BulkEnrollmentLog, error) {
	query := `
		INSERT INTO bulk_enrollment_logs (course_id, teacher_id, total_count, status)
		VALUES ($1, $2, $3, $4)
		RETURNING id, course_id, teacher_id, total_count, success_count, failed_count, status, error_message, created_at, completed_at
	`

	var result models.BulkEnrollmentLog
	err := r.db.QueryRowContext(ctx, query,
		log.CourseID,
		log.TeacherID,
		log.TotalCount,
		log.Status,
	).Scan(
		&result.ID,
		&result.CourseID,
		&result.TeacherID,
		&result.TotalCount,
		&result.SuccessCount,
		&result.FailedCount,
		&result.Status,
		&result.ErrorMessage,
		&result.CreatedAt,
		&result.CompletedAt,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to create bulk log: %w", err)
	}

	return &result, nil
}

// UpdateBulkLog updates bulk enrollment log
func (r *EnrollmentRepository) UpdateBulkLog(ctx context.Context, id int64, successCount, failedCount int, status string) error {
	query := `
		UPDATE bulk_enrollment_logs
		SET success_count = $1, failed_count = $2, status = $3, completed_at = CURRENT_TIMESTAMP
		WHERE id = $4
	`

	_, err := r.db.ExecContext(ctx, query, successCount, failedCount, status, id)
	return err
}
