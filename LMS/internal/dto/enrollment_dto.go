package dto

import "time"

// EnrollCourseRequest represents request to enroll in a course
type EnrollCourseRequest struct {
	CourseID int64 `json:"course_id" binding:"required"`
}

// EnrollmentResponse represents enrollment info
type EnrollmentResponse struct {
	ID         int64      `json:"id"`
	CourseID   int64      `json:"course_id"`
	StudentID  int64      `json:"student_id"`
	Status     string     `json:"status"` // WAITING, ACCEPTED, REJECTED
	EnrolledAt time.Time  `json:"enrolled_at"`
	AcceptedAt *time.Time `json:"accepted_at,omitempty"`
	RejectedAt *time.Time `json:"rejected_at,omitempty"`
	CreatedAt  time.Time  `json:"created_at"`
	UpdatedAt  time.Time  `json:"updated_at"`
}

// StudentEnrollmentResponse for student's view
type StudentEnrollmentResponse struct {
	ID          int64      `json:"id"`
	CourseID    int64      `json:"course_id"`
	CourseTitle string     `json:"course_title"`
	Status      string     `json:"status"`
	TeacherName string     `json:"teacher_name"`
	EnrolledAt  time.Time  `json:"enrolled_at"`
	AcceptedAt  *time.Time `json:"accepted_at,omitempty"`
}

// LearnerResponse for teacher's view of learners
type LearnerResponse struct {
	ID          int64      `json:"id"`
	CourseID    int64      `json:"course_id"`
	StudentID   int64      `json:"student_id"`
	StudentName string     `json:"student_name"`
	Email       string     `json:"email"`
	Status      string     `json:"status"`
	EnrolledAt  time.Time  `json:"enrolled_at"`
	AcceptedAt  *time.Time `json:"accepted_at,omitempty"`
}

// UpdateEnrollmentStatusRequest for accepting/rejecting enrollments
type UpdateEnrollmentStatusRequest struct {
	Status string `json:"status" binding:"required,oneof=ACCEPTED REJECTED"`
}

// BulkEnrollmentRequest for bulk enrolling students
type BulkEnrollmentRequest struct {
	CourseID  int64   `json:"course_id" binding:"required"`
	StudentID []int64 `json:"student_ids" binding:"required,min=1"`
}

// BulkEnrollmentResponse represents result of bulk operation
type BulkEnrollmentResponse struct {
	TotalCount int               `json:"total_count"`
	Succeeded  []int64           `json:"succeeded"`
	Failed     []EnrollmentError `json:"failed"`
}

// EnrollmentError represents error for a single enrollment
type EnrollmentError struct {
	StudentID int64  `json:"student_id"`
	Error     string `json:"error"`
}
