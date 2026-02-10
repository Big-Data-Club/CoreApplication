package models

import (
	"database/sql"
	"time"
)

// Enrollment represents a student enrollment in a course
type Enrollment struct {
	ID         int64        `json:"id" db:"id"`
	CourseID   int64        `json:"course_id" db:"course_id"`
	StudentID  int64        `json:"student_id" db:"student_id"`
	Status     string       `json:"status" db:"status"` // WAITING, ACCEPTED, REJECTED
	EnrolledAt time.Time    `json:"enrolled_at" db:"enrolled_at"`
	AcceptedAt sql.NullTime `json:"accepted_at" db:"accepted_at"`
	RejectedAt sql.NullTime `json:"rejected_at" db:"rejected_at"`
	CreatedAt  time.Time    `json:"created_at" db:"created_at"`
	UpdatedAt  time.Time    `json:"updated_at" db:"updated_at"`
}

// EnrollmentWithCourse includes course information
type EnrollmentWithCourse struct {
	Enrollment
	CourseTitle   string `json:"course_title" db:"course_title"`
	TeacherName   string `json:"teacher_name" db:"teacher_name"`
	TeacherEmail  string `json:"teacher_email" db:"teacher_email"`
}

// EnrollmentWithStudent includes student information
type EnrollmentWithStudent struct {
	Enrollment
	StudentName  string `json:"student_name" db:"student_name"`
	StudentEmail string `json:"student_email" db:"student_email"`
}

// Enrollment status constants
const (
	EnrollmentWaiting  = "WAITING"
	EnrollmentAccepted = "ACCEPTED"
	EnrollmentRejected = "REJECTED"
)

// BulkEnrollmentLog represents a bulk enrollment operation
type BulkEnrollmentLog struct {
	ID             int64        `json:"id" db:"id"`
	CourseID       int64        `json:"course_id" db:"course_id"`
	TeacherID      int64        `json:"teacher_id" db:"teacher_id"`
	TotalCount     int          `json:"total_count" db:"total_count"`
	SuccessCount   int          `json:"success_count" db:"success_count"`
	FailedCount    int          `json:"failed_count" db:"failed_count"`
	Status         string       `json:"status" db:"status"` // PROCESSING, COMPLETED, FAILED
	ErrorMessage   sql.NullString `json:"error_message" db:"error_message"`
	CreatedAt      time.Time    `json:"created_at" db:"created_at"`
	CompletedAt    sql.NullTime `json:"completed_at" db:"completed_at"`
}
