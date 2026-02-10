package service

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
)

type EnrollmentService struct {
	enrollmentRepo *repository.EnrollmentRepository
	courseRepo     *repository.CourseRepository
	userRepo       *repository.UserRepository
}

func NewEnrollmentService(
	enrollmentRepo *repository.EnrollmentRepository,
	courseRepo *repository.CourseRepository,
	userRepo *repository.UserRepository,
) *EnrollmentService {
	return &EnrollmentService{
		enrollmentRepo: enrollmentRepo,
		courseRepo:     courseRepo,
		userRepo:       userRepo,
	}
}

// EnrollCourse enrolls a student in a course
func (s *EnrollmentService) EnrollCourse(ctx context.Context, courseID, studentID int64) (*dto.EnrollmentResponse, error) {
	// Check if course exists
	_, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil {
		return nil, fmt.Errorf("course not found")
	}

	// Check if already enrolled
	existing, _ := s.enrollmentRepo.GetByStudentAndCourse(ctx, studentID, courseID)
	if existing != nil {
		return nil, fmt.Errorf("student already enrolled in this course")
	}

	// Create enrollment with WAITING status
	enrollment := &models.Enrollment{
		CourseID:  courseID,
		StudentID: studentID,
		Status:    models.EnrollmentWaiting,
	}

	result, err := s.enrollmentRepo.Create(ctx, enrollment)
	if err != nil {
		return nil, err
	}

	return toEnrollmentResponse(result), nil
}

// GetMyEnrollments gets all enrollments for a student
func (s *EnrollmentService) GetMyEnrollments(ctx context.Context, studentID int64, status string) ([]*dto.StudentEnrollmentResponse, error) {
	enrollments, err := s.enrollmentRepo.ListByStudent(ctx, studentID, status)
	if err != nil {
		return nil, err
	}

	var responses []*dto.StudentEnrollmentResponse
	for _, e := range enrollments {
		responses = append(responses, &dto.StudentEnrollmentResponse{
			ID:          e.ID,
			CourseID:    e.CourseID,
			CourseTitle: e.CourseTitle,
			Status:      e.Status,
			TeacherName: e.TeacherName,
			EnrolledAt:  e.EnrolledAt,
			AcceptedAt:  extractTime(e.AcceptedAt),
		})
	}

	return responses, nil
}

// GetCourseLearners gets all learners in a course
func (s *EnrollmentService) GetCourseLearners(ctx context.Context, courseID int64, status string, userID int64, role string) ([]*dto.LearnerResponse, error) {
	// Check if user is course creator (teacher)
	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil {
		return nil, fmt.Errorf("course not found")
	}

	if course.CreatedBy != userID && role != "ADMIN" {
		return nil, fmt.Errorf("unauthorized: only course creator can view learners")
	}

	enrollments, err := s.enrollmentRepo.ListByCourse(ctx, courseID, status)
	if err != nil {
		return nil, err
	}

	var responses []*dto.LearnerResponse
	for _, e := range enrollments {
		responses = append(responses, &dto.LearnerResponse{
			ID:          e.ID,
			CourseID:    e.CourseID,
			StudentID:   e.StudentID,
			StudentName: e.StudentName,
			Email:       e.StudentEmail,
			Status:      e.Status,
			EnrolledAt:  e.EnrolledAt,
			AcceptedAt:  extractTime(e.AcceptedAt),
		})
	}

	return responses, nil
}

// AcceptEnrollment accepts an enrollment request
func (s *EnrollmentService) AcceptEnrollment(ctx context.Context, enrollmentID, courseID int64, userID int64, role string) error {
	// Verify user is course creator
	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil {
		return fmt.Errorf("course not found")
	}

	if course.CreatedBy != userID && role != "ADMIN" {
		return fmt.Errorf("unauthorized")
	}

	return s.enrollmentRepo.UpdateStatus(ctx, enrollmentID, models.EnrollmentAccepted)
}

// RejectEnrollment rejects an enrollment request
func (s *EnrollmentService) RejectEnrollment(ctx context.Context, enrollmentID, courseID int64, userID int64, role string) error {
	// Verify user is course creator
	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil {
		return fmt.Errorf("course not found")
	}

	if course.CreatedBy != userID && role != "ADMIN" {
		return fmt.Errorf("unauthorized")
	}

	return s.enrollmentRepo.UpdateStatus(ctx, enrollmentID, models.EnrollmentRejected)
}

// BulkEnroll enrolls multiple students in a course
func (s *EnrollmentService) BulkEnroll(ctx context.Context, courseID int64, studentIDs []int64, teacherID int64, role string) *dto.BulkEnrollmentResponse {
	// Verify course exists and user is creator
	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil || (course.CreatedBy != teacherID && role != "ADMIN") {
		return &dto.BulkEnrollmentResponse{
			TotalCount: len(studentIDs),
			Succeeded:  []int64{},
			Failed: []dto.EnrollmentError{
				{StudentID: 0, Error: "unauthorized or course not found"},
			},
		}
	}

	response := &dto.BulkEnrollmentResponse{
		TotalCount: len(studentIDs),
		Succeeded:  []int64{},
		Failed:     []dto.EnrollmentError{},
	}

	// Create enrollment for each student
	for _, studentID := range studentIDs {
		// Check if already enrolled
		existing, _ := s.enrollmentRepo.GetByStudentAndCourse(ctx, studentID, courseID)
		if existing != nil {
			response.Failed = append(response.Failed, dto.EnrollmentError{
				StudentID: studentID,
				Error:     "already enrolled",
			})
			continue
		}

		// Create enrollment
		enrollment := &models.Enrollment{
			CourseID:  courseID,
			StudentID: studentID,
			Status:    models.EnrollmentAccepted, // Bulk by teacher = auto accept
		}

		result, err := s.enrollmentRepo.Create(ctx, enrollment)
		if err != nil {
			response.Failed = append(response.Failed, dto.EnrollmentError{
				StudentID: studentID,
				Error:     err.Error(),
			})
		} else {
			response.Succeeded = append(response.Succeeded, result.StudentID)
		}
	}

	return response
}

// CancelEnrollment allows student to cancel their enrollment
func (s *EnrollmentService) CancelEnrollment(ctx context.Context, enrollmentID int64, studentID int64) error {
	enrollment, err := s.enrollmentRepo.GetByID(ctx, enrollmentID)
	if err != nil {
		return fmt.Errorf("enrollment not found")
	}

	if enrollment.StudentID != studentID {
		return fmt.Errorf("unauthorized")
	}

	// Can only cancel if status is WAITING
	if enrollment.Status != models.EnrollmentWaiting {
		return fmt.Errorf("can only cancel pending enrollments")
	}

	return s.enrollmentRepo.Delete(ctx, enrollmentID)
}

// Helper functions

func toEnrollmentResponse(e *models.Enrollment) *dto.EnrollmentResponse {
	return &dto.EnrollmentResponse{
		ID:         e.ID,
		CourseID:   e.CourseID,
		StudentID:  e.StudentID,
		Status:     e.Status,
		EnrolledAt: e.EnrolledAt,
		AcceptedAt: extractTime(e.AcceptedAt),
		RejectedAt: extractTime(e.RejectedAt),
		CreatedAt:  e.CreatedAt,
		UpdatedAt:  e.UpdatedAt,
	}
}

func extractTime(t sql.NullTime) *time.Time {
	if t.Valid {
		return &t.Time
	}
	return nil
}
