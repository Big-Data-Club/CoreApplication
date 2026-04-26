package service

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/cache"
)

// enrollmentMembershipTTL caps how long a "is X enrolled in Y?" answer can
// stay cached. The endpoint is hit on most authenticated requests, but a
// teacher accept/reject must take effect quickly.
const enrollmentMembershipTTL = 1 * time.Minute

type EnrollmentService struct {
	enrollmentRepo *repository.EnrollmentRepository
	courseRepo     *repository.CourseRepository
	userRepo       *repository.UserRepository
	progressRepo   *repository.ProgressRepository
	cache          *cache.RedisCache
	loader         *cache.Loader
}

func NewEnrollmentService(
	enrollmentRepo *repository.EnrollmentRepository,
	courseRepo *repository.CourseRepository,
	userRepo *repository.UserRepository,
	progressRepo *repository.ProgressRepository,
	c *cache.RedisCache,
) *EnrollmentService {
	return &EnrollmentService{
		enrollmentRepo: enrollmentRepo,
		courseRepo:     courseRepo,
		userRepo:       userRepo,
		progressRepo:   progressRepo,
		cache:          c,
		loader:         cache.NewLoader(c),
	}
}

// CachedMembership is the small payload we cache for the membership check —
// it's intentionally narrower than the full enrollment row so that unrelated
// changes (rejected_at, updated_at, …) do not invalidate it.
//
// Exported because CourseService reads the same cache key directly when
// checking section/content visibility for students.
type CachedMembership struct {
	ID     int64  `json:"id"`
	Status string `json:"status"`
	Found  bool   `json:"found"`
}

// LoadMembership returns the cached membership for (student, course), loading
// from the repository on a miss. A "not enrolled" answer is cached as
// `Found=false` so a missing row doesn't keep hitting the database every time
// a guest browses a public course.
//
// Exported as a package-level function on the cache layer so any service that
// holds a *cache.RedisCache + enrollment repo can answer the same question
// with the same payload shape — keeping the Redis key contract uniform across
// callers.
func LoadMembership(
	ctx context.Context,
	loader *cache.Loader,
	repo *repository.EnrollmentRepository,
	studentID, courseID int64,
) (CachedMembership, error) {
	return cache.GetOrLoad(ctx, loader,
		cache.KeyStudentCourseEnrollment(studentID, courseID),
		enrollmentMembershipTTL,
		func(ctx context.Context) (CachedMembership, error) {
			e, err := repo.GetByStudentAndCourse(ctx, studentID, courseID)
			if err != nil {
				if err == sql.ErrNoRows {
					return CachedMembership{Found: false}, nil
				}
				return CachedMembership{}, err
			}
			return CachedMembership{ID: e.ID, Status: e.Status, Found: true}, nil
		})
}

func (s *EnrollmentService) getMembershipCached(ctx context.Context, studentID, courseID int64) (CachedMembership, error) {
	return LoadMembership(ctx, s.loader, s.enrollmentRepo, studentID, courseID)
}

func (s *EnrollmentService) invalidateMembership(ctx context.Context, studentID, courseID int64) {
	cache.Invalidate(ctx, s.cache, cache.KeyStudentCourseEnrollment(studentID, courseID))
}

// EnrollCourse enrolls a student in a course.
func (s *EnrollmentService) EnrollCourse(ctx context.Context, courseID, studentID int64) (*dto.EnrollmentResponse, error) {
	if _, err := s.courseRepo.GetByID(ctx, courseID); err != nil {
		return nil, fmt.Errorf("course not found")
	}

	// Use the live repository (not the cache) for the duplicate check: stale
	// "not enrolled" entries in Redis would otherwise let the same student
	// attempt to enroll twice within the cache window.
	if existing, _ := s.enrollmentRepo.GetByStudentAndCourse(ctx, studentID, courseID); existing != nil {
		return nil, fmt.Errorf("student already enrolled in this course")
	}

	enrollment := &models.Enrollment{
		CourseID:  courseID,
		StudentID: studentID,
		Status:    models.EnrollmentAccepted,
	}

	result, err := s.enrollmentRepo.Create(ctx, enrollment)
	if err != nil {
		return nil, err
	}

	s.invalidateMembership(ctx, studentID, courseID)
	return toEnrollmentResponse(result), nil
}

// GetMyEnrollments returns all enrollments for a student, optionally filtered
// by status, with progress percentages.
func (s *EnrollmentService) GetMyEnrollments(ctx context.Context, studentID int64, status string) ([]*dto.StudentEnrollmentResponse, error) {
	enrollments, err := s.enrollmentRepo.ListByStudent(ctx, studentID, status)
	if err != nil {
		return nil, err
	}

	if len(enrollments) == 0 {
		return []*dto.StudentEnrollmentResponse{}, nil
	}

	courseIDs := make([]int64, len(enrollments))
	for i, e := range enrollments {
		courseIDs[i] = e.CourseID
	}

	progressMap, err := s.progressRepo.GetBatchCourseProgress(ctx, courseIDs, studentID)
	if err != nil {
		progressMap = make(map[int64]*repository.CourseProgressResult)
	}

	responses := make([]*dto.StudentEnrollmentResponse, 0, len(enrollments))
	for _, e := range enrollments {
		pct := 0.0
		if p, ok := progressMap[e.CourseID]; ok && p != nil {
			pct = p.ProgressPercent
		}

		responses = append(responses, &dto.StudentEnrollmentResponse{
			ID:              e.ID,
			CourseID:        e.CourseID,
			CourseTitle:     e.CourseTitle,
			Status:          e.Status,
			TeacherName:     e.TeacherName,
			EnrolledAt:      e.EnrolledAt,
			AcceptedAt:      extractTime(e.AcceptedAt),
			ProgressPercent: pct,
		})
	}

	return responses, nil
}

// GetCourseLearners gets all learners enrolled in a course.
func (s *EnrollmentService) GetCourseLearners(ctx context.Context, courseID int64, status string, userID int64, role string) ([]*dto.LearnerResponse, error) {
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

	responses := make([]*dto.LearnerResponse, 0, len(enrollments))
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

// AcceptEnrollment accepts a student's enrollment request.
func (s *EnrollmentService) AcceptEnrollment(ctx context.Context, enrollmentID, courseID int64, userID int64, role string) error {
	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil {
		return fmt.Errorf("course not found")
	}

	if course.CreatedBy != userID && role != "ADMIN" {
		return fmt.Errorf("unauthorized")
	}

	if err := s.enrollmentRepo.UpdateStatus(ctx, enrollmentID, models.EnrollmentAccepted); err != nil {
		return err
	}
	if e, _ := s.enrollmentRepo.GetByID(ctx, enrollmentID); e != nil {
		s.invalidateMembership(ctx, e.StudentID, e.CourseID)
	}
	return nil
}

// RejectEnrollment rejects a student's enrollment request.
func (s *EnrollmentService) RejectEnrollment(ctx context.Context, enrollmentID, courseID int64, userID int64, role string) error {
	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil {
		return fmt.Errorf("course not found")
	}

	if course.CreatedBy != userID && role != "ADMIN" {
		return fmt.Errorf("unauthorized")
	}

	if err := s.enrollmentRepo.UpdateStatus(ctx, enrollmentID, models.EnrollmentRejected); err != nil {
		return err
	}
	if e, _ := s.enrollmentRepo.GetByID(ctx, enrollmentID); e != nil {
		s.invalidateMembership(ctx, e.StudentID, e.CourseID)
	}
	return nil
}

// BulkEnroll enrolls multiple students in a course with a single batch INSERT.
func (s *EnrollmentService) BulkEnroll(
	ctx context.Context,
	courseID int64,
	studentIDs []int64,
	teacherID int64,
	role string,
) *dto.BulkEnrollmentResponse {
	total := len(studentIDs)

	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil || (course.CreatedBy != teacherID && role != "ADMIN") {
		return &dto.BulkEnrollmentResponse{
			TotalCount: total,
			Succeeded:  []int64{},
			Failed:     []dto.EnrollmentError{{StudentID: 0, Error: "unauthorized or course not found"}},
		}
	}

	inserted, err := s.enrollmentRepo.BulkCreate(ctx, courseID, studentIDs)
	if err != nil {
		failed := make([]dto.EnrollmentError, total)
		for i, sid := range studentIDs {
			failed[i] = dto.EnrollmentError{StudentID: sid, Error: err.Error()}
		}
		return &dto.BulkEnrollmentResponse{
			TotalCount: total,
			Succeeded:  []int64{},
			Failed:     failed,
		}
	}

	insertedSet := make(map[int64]struct{}, len(inserted))
	for _, sid := range inserted {
		insertedSet[sid] = struct{}{}
		s.invalidateMembership(ctx, sid, courseID)
	}

	failed := make([]dto.EnrollmentError, 0, total-len(inserted))
	for _, sid := range studentIDs {
		if _, ok := insertedSet[sid]; !ok {
			failed = append(failed, dto.EnrollmentError{
				StudentID: sid,
				Error:     "already enrolled",
			})
		}
	}

	return &dto.BulkEnrollmentResponse{
		TotalCount: total,
		Succeeded:  inserted,
		Failed:     failed,
	}
}

// CancelEnrollment allows a student to cancel their own enrollment.
func (s *EnrollmentService) CancelEnrollment(ctx context.Context, enrollmentID int64, studentID int64) error {
	enrollment, err := s.enrollmentRepo.GetByID(ctx, enrollmentID)
	if err != nil {
		return fmt.Errorf("enrollment not found")
	}

	if enrollment.StudentID != studentID {
		return fmt.Errorf("unauthorized")
	}

	if err := s.enrollmentRepo.Delete(ctx, enrollmentID); err != nil {
		return err
	}
	s.invalidateMembership(ctx, enrollment.StudentID, enrollment.CourseID)
	return nil
}

// VerifyAccess checks if a user has access to a course (enrolled ACCEPTED,
// creator, or ADMIN). This is the gate behind every protected resource view,
// so it sits behind the membership cache to avoid a database round-trip per
// request.
func (s *EnrollmentService) VerifyAccess(ctx context.Context, userID, courseID int64, role string) error {
	if role == "ADMIN" {
		return nil
	}

	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil {
		return fmt.Errorf("course not found: %w", err)
	}
	if course.CreatedBy == userID {
		return nil
	}

	mem, err := s.getMembershipCached(ctx, userID, courseID)
	if err != nil {
		return fmt.Errorf("failed to verify membership: %w", err)
	}
	if !mem.Found {
		return fmt.Errorf("student not enrolled")
	}
	if mem.Status != models.EnrollmentAccepted {
		return fmt.Errorf("enrollment is %s, not ACCEPTED", mem.Status)
	}
	return nil
}

// ── helpers ───────────────────────────────────────────────────────────────────

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