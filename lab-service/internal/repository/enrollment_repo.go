package repository

import (
	"context"
	"database/sql"
	"fmt"

	"lab-service/internal/dto"
)

type EnrollmentRepository struct{ db *sql.DB }

func NewEnrollmentRepository(db *sql.DB) *EnrollmentRepository {
	return &EnrollmentRepository{db: db}
}

func (r *EnrollmentRepository) Enroll(ctx context.Context, labID, userID int64) (int64, error) {
	var id int64
	err := r.db.QueryRowContext(ctx,
		`INSERT INTO lab_enrollments (lab_id, user_id, status)
		VALUES ($1, $2, 'ACCEPTED')
		ON CONFLICT (lab_id, user_id) DO NOTHING
		RETURNING id`,
		labID, userID,
	).Scan(&id)
	if err == sql.ErrNoRows {
		// Already enrolled
		return 0, nil
	}
	return id, err
}

func (r *EnrollmentRepository) IsEnrolled(ctx context.Context, labID, userID int64) (bool, error) {
	var exists bool
	err := r.db.QueryRowContext(ctx,
		`SELECT EXISTS(SELECT 1 FROM lab_enrollments WHERE lab_id = $1 AND user_id = $2 AND status = 'ACCEPTED')`,
		labID, userID,
	).Scan(&exists)
	return exists, err
}

func (r *EnrollmentRepository) GetLabLearners(ctx context.Context, labID int64, status string) ([]map[string]interface{}, error) {
	query := `SELECT e.id, e.user_id, e.status, e.enrolled_at, u.full_name, u.email
		FROM lab_enrollments e
		JOIN users u ON u.id = e.user_id
		WHERE e.lab_id = $1`
	args := []interface{}{labID}

	if status != "" {
		query += " AND e.status = $2"
		args = append(args, status)
	}
	query += " ORDER BY e.enrolled_at DESC"

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var learners []map[string]interface{}
	for rows.Next() {
		var id, userID int64
		var st, name, email string
		var enrolledAt interface{}
		rows.Scan(&id, &userID, &st, &enrolledAt, &name, &email)
		learners = append(learners, map[string]interface{}{
			"id": id, "user_id": userID, "status": st,
			"enrolled_at": enrolledAt, "full_name": name, "email": email,
		})
	}
	return learners, nil
}

func (r *EnrollmentRepository) GetMyLabEnrollments(ctx context.Context, userID int64) ([]map[string]interface{}, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT e.id, e.lab_id, e.status, e.enrolled_at,
			l.title, l.lab_type, l.level, l.category, l.thumbnail_url
		FROM lab_enrollments e
		JOIN labs l ON l.id = e.lab_id
		WHERE e.user_id = $1 AND e.status = 'ACCEPTED'
		ORDER BY e.enrolled_at DESC`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var enrollments []map[string]interface{}
	for rows.Next() {
		var eid, labID int64
		var st, title, labType, level, category, thumb string
		var enrolledAt interface{}
		rows.Scan(&eid, &labID, &st, &enrolledAt, &title, &labType, &level, &category, &thumb)
		enrollments = append(enrollments, map[string]interface{}{
			"id": eid, "lab_id": labID, "status": st, "enrolled_at": enrolledAt,
			"title": title, "lab_type": labType, "level": level,
			"category": category, "thumbnail_url": thumb,
		})
	}
	return enrollments, nil
}

func (r *EnrollmentRepository) Cancel(ctx context.Context, enrollmentID, userID int64) error {
	result, err := r.db.ExecContext(ctx,
		"DELETE FROM lab_enrollments WHERE id = $1 AND user_id = $2", enrollmentID, userID)
	if err != nil {
		return err
	}
	n, _ := result.RowsAffected()
	if n == 0 {
		return fmt.Errorf("enrollment not found or not owned by user")
	}
	return nil
}

func (r *EnrollmentRepository) BulkEnroll(ctx context.Context, labID int64, userIDs []int64) (int, error) {
	count := 0
	for _, uid := range userIDs {
		_, err := r.db.ExecContext(ctx,
			`INSERT INTO lab_enrollments (lab_id, user_id, status)
			VALUES ($1, $2, 'ACCEPTED')
			ON CONFLICT (lab_id, user_id) DO NOTHING`,
			labID, uid)
		if err == nil {
			count++
		}
	}
	return count, nil
}
