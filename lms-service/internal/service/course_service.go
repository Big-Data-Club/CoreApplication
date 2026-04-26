package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/cache"
)

// TTLs for course-related cache entries.
//
// The list TTL is intentionally short: published-course discovery is the most
// visible page on the LMS, so we accept a 2-minute staleness window in
// exchange for absorbing traffic spikes (course-catalog browsing). Detail
// TTLs are longer because individual courses change rarely once published,
// and writes invalidate the entry explicitly.
const (
	courseListCacheTTL     = 2 * time.Minute
	courseCacheTTL         = 5 * time.Minute
	sectionListCacheTTL    = 2 * time.Minute
	sectionCacheTTL        = 5 * time.Minute
	contentListCacheTTL    = 2 * time.Minute
	contentCacheTTL        = 5 * time.Minute
)

type CourseService struct {
	courseRepo     *repository.CourseRepository
	userRepo       *repository.UserRepository
	enrollmentRepo *repository.EnrollmentRepository
	cache          *cache.RedisCache
	loader         *cache.Loader
}

func NewCourseService(
	courseRepo *repository.CourseRepository,
	userRepo *repository.UserRepository,
	enrollmentRepo *repository.EnrollmentRepository,
	c *cache.RedisCache,
) *CourseService {
	return &CourseService{
		courseRepo:     courseRepo,
		userRepo:       userRepo,
		enrollmentRepo: enrollmentRepo,
		cache:          c,
		loader:         cache.NewLoader(c),
	}
}

// ── cache-aware repository wrappers ───────────────────────────────────────────
//
// These thin wrappers replace direct repository calls inside the service. They
// implement the cache-aside pattern with single-flight protection (see
// pkg/cache/loader.go) and are the ONLY place the service should fetch course
// / section / content rows. That way invalidation only needs to target a
// well-known set of keys.

func (s *CourseService) getCourseCached(ctx context.Context, courseID int64) (*models.CourseWithCreator, error) {
	return cache.GetOrLoad(ctx, s.loader, cache.KeyCourse(courseID), courseCacheTTL,
		func(ctx context.Context) (*models.CourseWithCreator, error) {
			return s.courseRepo.GetByID(ctx, courseID)
		})
}

func (s *CourseService) getSectionCached(ctx context.Context, sectionID int64) (*models.CourseSection, error) {
	return cache.GetOrLoad(ctx, s.loader, cache.KeySection(sectionID), sectionCacheTTL,
		func(ctx context.Context) (*models.CourseSection, error) {
			return s.courseRepo.GetSectionByID(ctx, sectionID)
		})
}

func (s *CourseService) getContentCached(ctx context.Context, contentID int64) (*models.SectionContent, error) {
	return cache.GetOrLoad(ctx, s.loader, cache.KeyContent(contentID), contentCacheTTL,
		func(ctx context.Context) (*models.SectionContent, error) {
			return s.courseRepo.GetContentByID(ctx, contentID)
		})
}

// CreateCourse creates a new course and invalidates the published-list cache.
func (s *CourseService) CreateCourse(ctx context.Context, req *dto.CreateCourseRequest, creatorID int64) (*dto.CourseResponse, error) {
	course := &models.Course{
		Title:        req.Title,
		Description:  sql.NullString{String: req.Description, Valid: req.Description != ""},
		Category:     sql.NullString{String: req.Category, Valid: req.Category != ""},
		Level:        sql.NullString{String: req.Level, Valid: req.Level != ""},
		ThumbnailURL: sql.NullString{String: req.ThumbnailURL, Valid: req.ThumbnailURL != ""},
		Status:       models.CourseStatusDraft,
		CreatedBy:    creatorID,
	}

	created, err := s.courseRepo.Create(ctx, course)
	if err != nil {
		return nil, fmt.Errorf("failed to create course: %w", err)
	}

	return s.toCourseResponse(created), nil
}

// GetCourse retrieves a course by ID.
func (s *CourseService) GetCourse(ctx context.Context, courseID int64, userID int64, role string) (*dto.CourseResponse, error) {
	course, err := s.getCourseCached(ctx, courseID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("course not found")
		}
		return nil, fmt.Errorf("failed to get course: %w", err)
	}

	if course.Status == models.CourseStatusDraft {
		if role != models.RoleAdmin && course.CreatedBy != userID {
			return nil, fmt.Errorf("unauthorized to view this course")
		}
	}

	return s.toCourseResponseWithCreator(course), nil
}

// UpdateCourse updates a course and invalidates related cache entries.
func (s *CourseService) UpdateCourse(ctx context.Context, courseID int64, req *dto.UpdateCourseRequest, userID int64, role string) error {
	course, err := s.getCourseCached(ctx, courseID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("course not found")
		}
		return fmt.Errorf("failed to get course: %w", err)
	}

	if role != models.RoleAdmin && course.CreatedBy != userID {
		return fmt.Errorf("unauthorized to update this course")
	}

	updates := make(map[string]interface{})
	if req.Title != nil {
		updates["title"] = *req.Title
	}
	if req.Description != nil {
		updates["description"] = *req.Description
	}
	if req.Category != nil {
		updates["category"] = *req.Category
	}
	if req.Level != nil {
		updates["level"] = *req.Level
	}
	if req.ThumbnailURL != nil {
		updates["thumbnail_url"] = *req.ThumbnailURL
	}

	if len(updates) == 0 {
		return fmt.Errorf("no fields to update")
	}

	if err := s.courseRepo.Update(ctx, courseID, updates); err != nil {
		return fmt.Errorf("failed to update course: %w", err)
	}

	s.invalidateCourseCache(ctx, courseID)
	return nil
}

// DeleteCourse deletes a course and invalidates related cache entries.
func (s *CourseService) DeleteCourse(ctx context.Context, courseID int64, userID int64, role string) error {
	course, err := s.getCourseCached(ctx, courseID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("course not found")
		}
		return fmt.Errorf("failed to get course: %w", err)
	}

	if role != models.RoleAdmin && course.CreatedBy != userID {
		return fmt.Errorf("unauthorized to delete this course")
	}

	if err := s.courseRepo.Delete(ctx, courseID); err != nil {
		return fmt.Errorf("failed to delete course: %w", err)
	}

	s.invalidateCourseCache(ctx, courseID)
	return nil
}

// PublishCourse publishes a course and invalidates related cache entries.
func (s *CourseService) PublishCourse(ctx context.Context, courseID int64, userID int64, role string) error {
	course, err := s.getCourseCached(ctx, courseID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("course not found")
		}
		return fmt.Errorf("failed to get course: %w", err)
	}

	if role != models.RoleAdmin && course.CreatedBy != userID {
		return fmt.Errorf("unauthorized to publish this course")
	}

	if err := s.courseRepo.Publish(ctx, courseID); err != nil {
		return fmt.Errorf("failed to publish course: %w", err)
	}

	// Invalidate both the specific course and the published list so the newly
	// published course appears immediately.
	s.invalidateCourseCache(ctx, courseID)
	return nil
}

// ListMyCourses lists courses created by the user.
func (s *CourseService) ListMyCourses(ctx context.Context, userID int64) ([]*dto.CourseResponse, error) {
	courses, err := s.courseRepo.ListByCreator(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("failed to list courses: %w", err)
	}

	result := make([]*dto.CourseResponse, 0, len(courses))
	for _, course := range courses {
		result = append(result, s.toCourseResponseWithCreator(course))
	}

	return result, nil
}

// ListPublishedCourses lists all published courses.
//
// This is the most-trafficked endpoint on the LMS (catalogue browsing). The
// cache-aside + single-flight pattern means a stampede on cache expiry only
// produces ONE database query per process, even if hundreds of requests are
// in flight at the moment of expiration.
func (s *CourseService) ListPublishedCourses(ctx context.Context) ([]*dto.CourseResponse, error) {
	return cache.GetOrLoad(ctx, s.loader, cache.KeyCourseList, courseListCacheTTL,
		func(ctx context.Context) ([]*dto.CourseResponse, error) {
			courses, err := s.courseRepo.ListPublished(ctx)
			if err != nil {
				return nil, fmt.Errorf("failed to list published courses: %w", err)
			}
			result := make([]*dto.CourseResponse, 0, len(courses))
			for _, course := range courses {
				result = append(result, s.toCourseResponseWithCreator(course))
			}
			return result, nil
		})
}

func (s *CourseService) CreateSection(ctx context.Context, courseID int64, req *dto.CreateSectionRequest, userID int64, role string) (*dto.SectionResponse, error) {
	course, err := s.getCourseCached(ctx, courseID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("course not found")
		}
		return nil, fmt.Errorf("failed to get course: %w", err)
	}

	if role != models.RoleAdmin && course.CreatedBy != userID {
		return nil, fmt.Errorf("unauthorized to create section in this course")
	}

	section := &models.CourseSection{
		CourseID:    courseID,
		Title:       req.Title,
		Description: sql.NullString{String: req.Description, Valid: req.Description != ""},
		OrderIndex:  req.OrderIndex,
		IsPublished: false,
	}

	created, err := s.courseRepo.CreateSection(ctx, section)
	if err != nil {
		return nil, fmt.Errorf("failed to create section: %w", err)
	}

	// New section means the cached section list for this course is stale.
	cache.Invalidate(ctx, s.cache, cache.KeyCourseSections(courseID))
	return s.toSectionResponse(created), nil
}

func (s *CourseService) GetSection(ctx context.Context, sectionID int64, userID int64, role string) (*dto.SectionResponse, error) {
	section, err := s.getSectionCached(ctx, sectionID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("section not found")
		}
		return nil, fmt.Errorf("failed to get section: %w", err)
	}

	course, err := s.getCourseCached(ctx, section.CourseID)
	if err != nil {
		return nil, fmt.Errorf("failed to get course: %w", err)
	}

	if !section.IsPublished && role != models.RoleAdmin && role != models.RoleTeacher && course.CreatedBy != userID {
		if role == models.RoleStudent {
			enrollment, _ := s.enrollmentRepo.GetByStudentAndCourse(ctx, userID, course.ID)
			if enrollment == nil || enrollment.Status != models.EnrollmentAccepted {
				return nil, fmt.Errorf("unauthorized to view this section")
			}
		} else {
			return nil, fmt.Errorf("unauthorized to view this section")
		}
	}

	return s.toSectionResponse(section), nil
}

// ListSections returns sections for a course (lazy-loading entry point: the
// caller fetches contents per-section only when needed).
//
// Caching strategy: we cache the FULL section list keyed by courseID — all
// sections regardless of visibility. The visibility filter is applied per
// caller because it depends on (userID, role, enrollment state). This keeps
// the cache hit rate high and avoids storing per-user permutations.
func (s *CourseService) ListSections(ctx context.Context, courseID int64, userID int64, role string) ([]*dto.SectionResponse, error) {
	course, err := s.getCourseCached(ctx, courseID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("course not found")
		}
		return nil, fmt.Errorf("failed to get course: %w", err)
	}

	sections, err := cache.GetOrLoad(ctx, s.loader, cache.KeyCourseSections(courseID), sectionListCacheTTL,
		func(ctx context.Context) ([]*models.CourseSection, error) {
			return s.courseRepo.ListSectionsByCourse(ctx, courseID)
		})
	if err != nil {
		return nil, fmt.Errorf("failed to list sections: %w", err)
	}

	isEnrolled := false
	if role == models.RoleStudent {
		isEnrolled = s.isStudentEnrolled(ctx, userID, courseID)
	}

	result := make([]*dto.SectionResponse, 0, len(sections))
	for _, section := range sections {
		if !section.IsPublished {
			if role == models.RoleAdmin || role == models.RoleTeacher || course.CreatedBy == userID || (role == models.RoleStudent && isEnrolled) {
				result = append(result, s.toSectionResponse(section))
			}
		} else {
			result = append(result, s.toSectionResponse(section))
		}
	}

	return result, nil
}

func (s *CourseService) UpdateSection(ctx context.Context, sectionID int64, req *dto.UpdateSectionRequest, userID int64, role string) error {
	section, err := s.getSectionCached(ctx, sectionID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("section not found")
		}
		return fmt.Errorf("failed to get section: %w", err)
	}

	course, err := s.getCourseCached(ctx, section.CourseID)
	if err != nil {
		return fmt.Errorf("failed to get course: %w", err)
	}

	if role != models.RoleAdmin && course.CreatedBy != userID {
		return fmt.Errorf("unauthorized to update this section")
	}

	updates := make(map[string]interface{})
	if req.Title != nil {
		updates["title"] = *req.Title
	}
	if req.Description != nil {
		updates["description"] = *req.Description
	}
	if req.OrderIndex != nil {
		updates["order_index"] = *req.OrderIndex
	}
	if req.IsPublished != nil {
		updates["is_published"] = *req.IsPublished
	}

	if len(updates) == 0 {
		return fmt.Errorf("no fields to update")
	}

	if err := s.courseRepo.UpdateSection(ctx, sectionID, updates); err != nil {
		return err
	}

	cache.Invalidate(ctx, s.cache,
		cache.KeySection(sectionID),
		cache.KeyCourseSections(section.CourseID),
	)
	return nil
}

func (s *CourseService) DeleteSection(ctx context.Context, sectionID int64, userID int64, role string) error {
	section, err := s.getSectionCached(ctx, sectionID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("section not found")
		}
		return fmt.Errorf("failed to get section: %w", err)
	}

	course, err := s.getCourseCached(ctx, section.CourseID)
	if err != nil {
		return fmt.Errorf("failed to get course: %w", err)
	}

	if role != models.RoleAdmin && course.CreatedBy != userID {
		return fmt.Errorf("unauthorized to delete this section")
	}

	if err := s.courseRepo.DeleteSection(ctx, sectionID); err != nil {
		return err
	}

	// Cascading delete: also drop the section's content list cache, since
	// deleting the section orphans its contents from a caching perspective.
	cache.Invalidate(ctx, s.cache,
		cache.KeySection(sectionID),
		cache.KeyCourseSections(section.CourseID),
		cache.KeySectionContents(sectionID),
	)
	return nil
}

// ── Content methods ───────────────────────────────────────────────────────────

func (s *CourseService) CreateContent(ctx context.Context, sectionID int64, req *dto.CreateContentRequest, userID int64, role string) (*dto.ContentResponse, error) {
	section, err := s.getSectionCached(ctx, sectionID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("section not found")
		}
		return nil, fmt.Errorf("failed to get section: %w", err)
	}

	course, err := s.getCourseCached(ctx, section.CourseID)
	if err != nil {
		return nil, fmt.Errorf("failed to get course: %w", err)
	}

	if role != models.RoleAdmin && course.CreatedBy != userID {
		return nil, fmt.Errorf("unauthorized to create content in this section")
	}

	metadata, err := json.Marshal(req.Metadata)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal metadata: %w", err)
	}

	content := &models.SectionContent{
		SectionID:   sectionID,
		Type:        req.Type,
		Title:       req.Title,
		Description: sql.NullString{String: req.Description, Valid: req.Description != ""},
		OrderIndex:  req.OrderIndex,
		Metadata:    metadata,
		IsPublished: false,
		IsMandatory: req.IsMandatory,
		CreatedBy:   userID,
	}

	if req.Metadata != nil {
		if path, ok := req.Metadata["file_path"].(string); ok {
			content.FilePath = sql.NullString{String: path, Valid: true}
		}
		if size, ok := req.Metadata["file_size"].(float64); ok {
			content.FileSize = sql.NullInt64{Int64: int64(size), Valid: true}
		}
		if ftype, ok := req.Metadata["file_type"].(string); ok {
			content.FileType = sql.NullString{String: ftype, Valid: true}
		}
	}

	created, err := s.courseRepo.CreateContent(ctx, content)
	if err != nil {
		return nil, fmt.Errorf("failed to create content: %w", err)
	}

	cache.Invalidate(ctx, s.cache, cache.KeySectionContents(sectionID))
	return s.toContentResponse(created)
}

func (s *CourseService) GetContent(ctx context.Context, contentID int64, userID int64, role string) (*dto.ContentResponse, error) {
	content, err := s.getContentCached(ctx, contentID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("content not found")
		}
		return nil, fmt.Errorf("failed to get content: %w", err)
	}

	section, err := s.getSectionCached(ctx, content.SectionID)
	if err != nil {
		return nil, fmt.Errorf("failed to get section: %w", err)
	}

	course, err := s.getCourseCached(ctx, section.CourseID)
	if err != nil {
		return nil, fmt.Errorf("failed to get course: %w", err)
	}

	if !content.IsPublished && role != models.RoleAdmin && role != models.RoleTeacher && course.CreatedBy != userID {
		if role == models.RoleStudent {
			if !s.isStudentEnrolled(ctx, userID, course.ID) {
				return nil, fmt.Errorf("unauthorized to view this content")
			}
		} else {
			return nil, fmt.Errorf("unauthorized to view this content")
		}
	}

	return s.toContentResponse(content)
}

// ListContent returns content items inside a section. This is the lazy-loading
// payload requested when a user expands a section in the UI.
//
// Caching strategy mirrors ListSections: cache the unfiltered list keyed by
// sectionID, then apply visibility filtering per caller.
func (s *CourseService) ListContent(ctx context.Context, sectionID int64, userID int64, role string) ([]*dto.ContentResponse, error) {
	section, err := s.getSectionCached(ctx, sectionID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("section not found")
		}
		return nil, fmt.Errorf("failed to get section: %w", err)
	}

	course, err := s.getCourseCached(ctx, section.CourseID)
	if err != nil {
		return nil, fmt.Errorf("failed to get course: %w", err)
	}

	contents, err := cache.GetOrLoad(ctx, s.loader, cache.KeySectionContents(sectionID), contentListCacheTTL,
		func(ctx context.Context) ([]*models.SectionContent, error) {
			return s.courseRepo.ListContentBySection(ctx, sectionID)
		})
	if err != nil {
		return nil, fmt.Errorf("failed to list content: %w", err)
	}

	isEnrolled := false
	if role == models.RoleStudent {
		isEnrolled = s.isStudentEnrolled(ctx, userID, course.ID)
	}

	result := make([]*dto.ContentResponse, 0, len(contents))
	for _, content := range contents {
		if !content.IsPublished {
			if role == models.RoleAdmin || role == models.RoleTeacher || course.CreatedBy == userID || (role == models.RoleStudent && isEnrolled) {
				resp, err := s.toContentResponse(content)
				if err != nil {
					continue
				}
				result = append(result, resp)
			}
		} else {
			resp, err := s.toContentResponse(content)
			if err != nil {
				continue
			}
			result = append(result, resp)
		}
	}

	return result, nil
}

func (s *CourseService) UpdateContent(ctx context.Context, contentID int64, req *dto.UpdateContentRequest, userID int64, role string) error {
	content, err := s.getContentCached(ctx, contentID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("content not found")
		}
		return fmt.Errorf("failed to get content: %w", err)
	}

	section, err := s.getSectionCached(ctx, content.SectionID)
	if err != nil {
		return fmt.Errorf("failed to get section: %w", err)
	}

	course, err := s.getCourseCached(ctx, section.CourseID)
	if err != nil {
		return fmt.Errorf("failed to get course: %w", err)
	}

	if role != models.RoleAdmin && course.CreatedBy != userID {
		return fmt.Errorf("unauthorized to update this content")
	}

	updates := make(map[string]interface{})
	if req.Title != nil {
		updates["title"] = *req.Title
	}
	if req.Description != nil {
		updates["description"] = *req.Description
	}
	if req.OrderIndex != nil {
		updates["order_index"] = *req.OrderIndex
	}
	if req.Metadata != nil {
		metadata, err := json.Marshal(*req.Metadata)
		if err != nil {
			return fmt.Errorf("failed to marshal metadata: %w", err)
		}
		updates["metadata"] = metadata
	}
	if req.IsPublished != nil {
		updates["is_published"] = *req.IsPublished
	}
	if req.IsMandatory != nil {
		updates["is_mandatory"] = *req.IsMandatory
	}

	if req.Metadata != nil {
		if path, ok := (*req.Metadata)["file_path"].(string); ok {
			updates["file_path"] = path
		}
		if size, ok := (*req.Metadata)["file_size"].(float64); ok {
			updates["file_size"] = int64(size)
		}
		if ftype, ok := (*req.Metadata)["file_type"].(string); ok {
			updates["file_type"] = ftype
		}
	}

	if len(updates) == 0 {
		return fmt.Errorf("no fields to update")
	}

	if err := s.courseRepo.UpdateContent(ctx, contentID, updates); err != nil {
		return err
	}

	cache.Invalidate(ctx, s.cache,
		cache.KeyContent(contentID),
		cache.KeySectionContents(content.SectionID),
	)
	return nil
}

func (s *CourseService) DeleteContent(ctx context.Context, contentID int64, userID int64, role string) error {
	content, err := s.getContentCached(ctx, contentID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("content not found")
		}
		return fmt.Errorf("failed to get content: %w", err)
	}

	section, err := s.getSectionCached(ctx, content.SectionID)
	if err != nil {
		return fmt.Errorf("failed to get section: %w", err)
	}

	course, err := s.getCourseCached(ctx, section.CourseID)
	if err != nil {
		return fmt.Errorf("failed to get course: %w", err)
	}

	if role != models.RoleAdmin && course.CreatedBy != userID {
		return fmt.Errorf("unauthorized to delete this content")
	}

	if err := s.courseRepo.DeleteContent(ctx, contentID); err != nil {
		return err
	}

	cache.Invalidate(ctx, s.cache,
		cache.KeyContent(contentID),
		cache.KeySectionContents(content.SectionID),
	)
	return nil
}

// ── cache helpers ─────────────────────────────────────────────────────────────

// invalidateCourseCache removes cache entries for a specific course and the
// shared published-list key so the next read re-fetches from DB. The section
// list is also dropped — when a course is updated/deleted/published, the UI
// typically re-renders the course page and we don't want to serve sections
// referencing a stale course state.
func (s *CourseService) invalidateCourseCache(ctx context.Context, courseID int64) {
	// Fire-and-forget: cache invalidation failure is non-fatal — TTL takes over.
	_ = s.cache.Delete(ctx,
		cache.KeyCourse(courseID),
		cache.KeyCourseSections(courseID),
		cache.KeyCourseList,
	)
}

// isStudentEnrolled answers the membership question used by visibility checks
// in GetSection / ListSections / GetContent / ListContent. It is read on
// almost every authenticated student request, so it goes through the cache.
//
// We delegate to LoadMembership in enrollment_service.go so that the Redis
// payload shape and TTL stay identical across services that share the
// `enrollment:student:X:course:Y` key.
func (s *CourseService) isStudentEnrolled(ctx context.Context, studentID, courseID int64) bool {
	mem, err := LoadMembership(ctx, s.loader, s.enrollmentRepo, studentID, courseID)
	if err != nil {
		return false
	}
	return mem.Found && mem.Status == models.EnrollmentAccepted
}

// ── model-to-DTO converters ───────────────────────────────────────────────────

func (s *CourseService) toCourseResponse(course *models.Course) *dto.CourseResponse {
	resp := &dto.CourseResponse{
		ID:        course.ID,
		Title:     course.Title,
		Status:    course.Status,
		CreatedBy: course.CreatedBy,
		CreatedAt: course.CreatedAt,
		UpdatedAt: course.UpdatedAt,
	}

	if course.Description.Valid {
		resp.Description = course.Description.String
	}
	if course.Category.Valid {
		resp.Category = course.Category.String
	}
	if course.Level.Valid {
		resp.Level = course.Level.String
	}
	if course.ThumbnailURL.Valid {
		resp.ThumbnailURL = course.ThumbnailURL.String
	}
	if course.PublishedAt.Valid {
		resp.PublishedAt = &course.PublishedAt.Time
	}

	return resp
}

func (s *CourseService) toCourseResponseWithCreator(course *models.CourseWithCreator) *dto.CourseResponse {
	resp := s.toCourseResponse(&course.Course)
	resp.CreatorName = course.CreatorName
	resp.CreatorEmail = course.CreatorEmail
	return resp
}

func (s *CourseService) toSectionResponse(section *models.CourseSection) *dto.SectionResponse {
	resp := &dto.SectionResponse{
		ID:          section.ID,
		CourseID:    section.CourseID,
		Title:       section.Title,
		OrderIndex:  section.OrderIndex,
		IsPublished: section.IsPublished,
		CreatedAt:   section.CreatedAt,
		UpdatedAt:   section.UpdatedAt,
	}

	if section.Description.Valid {
		resp.Description = section.Description.String
	}

	return resp
}

func (s *CourseService) toContentResponse(content *models.SectionContent) (*dto.ContentResponse, error) {
	resp := &dto.ContentResponse{
		ID:          content.ID,
		SectionID:   content.SectionID,
		Type:        content.Type,
		Title:       content.Title,
		OrderIndex:  content.OrderIndex,
		IsPublished: content.IsPublished,
		IsMandatory: content.IsMandatory,
		CreatedBy:   content.CreatedBy,
		CreatedAt:   content.CreatedAt,
		UpdatedAt:   content.UpdatedAt,
	}

	if content.Description.Valid {
		resp.Description = content.Description.String
	}
	if content.FilePath.Valid {
		resp.FilePath = content.FilePath.String
	}
	if content.FileSize.Valid {
		resp.FileSize = content.FileSize.Int64
	}
	if content.FileType.Valid {
		resp.FileType = content.FileType.String
	}
	if content.AIIndexStatus.Valid {
		resp.AIIndexStatus = content.AIIndexStatus.String
	}

	if len(content.Metadata) > 0 {
		var metadata map[string]interface{}
		if err := json.Unmarshal(content.Metadata, &metadata); err == nil {
			resp.Metadata = metadata
		}
	}

	return resp, nil
}

