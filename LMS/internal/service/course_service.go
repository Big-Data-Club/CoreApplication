package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/cache"
)

type CourseService struct {
	courseRepo     *repository.CourseRepository
	userRepo       *repository.UserRepository
	enrollmentRepo *repository.EnrollmentRepository
	cache          *cache.RedisCache
}

func NewCourseService(
	courseRepo *repository.CourseRepository,
	userRepo *repository.UserRepository,
	enrollmentRepo *repository.EnrollmentRepository,
	cache *cache.RedisCache,
) *CourseService {
	return &CourseService{
		courseRepo:     courseRepo,
		userRepo:       userRepo,
		enrollmentRepo: enrollmentRepo,
		cache:          cache,
	}
}

// CreateCourse creates a new course
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

// GetCourse retrieves a course by ID
func (s *CourseService) GetCourse(ctx context.Context, courseID int64, userID int64, role string) (*dto.CourseResponse, error) {
	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("course not found")
		}
		return nil, fmt.Errorf("failed to get course: %w", err)
	}

	// Check permissions: only creator, teacher, or admin can see draft courses
	if course.Status == models.CourseStatusDraft {
		if role != models.RoleAdmin && course.CreatedBy != userID {
			return nil, fmt.Errorf("unauthorized to view this course")
		}
	}

	return s.toCourseResponseWithCreator(course), nil
}

// UpdateCourse updates a course
func (s *CourseService) UpdateCourse(ctx context.Context, courseID int64, req *dto.UpdateCourseRequest, userID int64, role string) error {
	// Get existing course
	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("course not found")
		}
		return fmt.Errorf("failed to get course: %w", err)
	}

	// Check permissions: only creator or admin can update
	if role != models.RoleAdmin && course.CreatedBy != userID {
		return fmt.Errorf("unauthorized to update this course")
	}

	// Build updates map
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

	err = s.courseRepo.Update(ctx, courseID, updates)
	if err != nil {
		return fmt.Errorf("failed to update course: %w", err)
	}

	// Clear cache
	s.cache.Delete(ctx, cache.KeyCourse(courseID))

	return nil
}

// DeleteCourse deletes a course
func (s *CourseService) DeleteCourse(ctx context.Context, courseID int64, userID int64, role string) error {
	// Get existing course
	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("course not found")
		}
		return fmt.Errorf("failed to get course: %w", err)
	}

	// Check permissions: only creator or admin can delete
	if role != models.RoleAdmin && course.CreatedBy != userID {
		return fmt.Errorf("unauthorized to delete this course")
	}

	err = s.courseRepo.Delete(ctx, courseID)
	if err != nil {
		return fmt.Errorf("failed to delete course: %w", err)
	}

	// Clear cache
	s.cache.Delete(ctx, cache.KeyCourse(courseID))

	return nil
}

// PublishCourse publishes a course
func (s *CourseService) PublishCourse(ctx context.Context, courseID int64, userID int64, role string) error {
	// Get existing course
	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("course not found")
		}
		return fmt.Errorf("failed to get course: %w", err)
	}

	// Check permissions: only creator or admin can publish
	if role != models.RoleAdmin && course.CreatedBy != userID {
		return fmt.Errorf("unauthorized to publish this course")
	}

	err = s.courseRepo.Publish(ctx, courseID)
	if err != nil {
		return fmt.Errorf("failed to publish course: %w", err)
	}

	// Clear cache
	s.cache.Delete(ctx, cache.KeyCourse(courseID))

	return nil
}

// ListMyCourses lists courses created by the user
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

// ListPublishedCourses lists all published courses
func (s *CourseService) ListPublishedCourses(ctx context.Context) ([]*dto.CourseResponse, error) {
	courses, err := s.courseRepo.ListPublished(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to list published courses: %w", err)
	}

	result := make([]*dto.CourseResponse, 0, len(courses))
	for _, course := range courses {
		result = append(result, s.toCourseResponseWithCreator(course))
	}

	return result, nil
}

// ===== SECTION METHODS =====

// CreateSection creates a new section in a course
func (s *CourseService) CreateSection(ctx context.Context, courseID int64, req *dto.CreateSectionRequest, userID int64, role string) (*dto.SectionResponse, error) {
	// Check if user owns the course or is admin
	course, err := s.courseRepo.GetByID(ctx, courseID)
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

	return s.toSectionResponse(created), nil
}

// GetSection retrieves a section by ID
func (s *CourseService) GetSection(ctx context.Context, sectionID int64, userID int64, role string) (*dto.SectionResponse, error) {
	section, err := s.courseRepo.GetSectionByID(ctx, sectionID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("section not found")
		}
		return nil, fmt.Errorf("failed to get section: %w", err)
	}

	// Check course permissions
	course, err := s.courseRepo.GetByID(ctx, section.CourseID)
	if err != nil {
		return nil, fmt.Errorf("failed to get course: %w", err)
	}

	if !section.IsPublished && role != models.RoleAdmin && course.CreatedBy != userID {
		return nil, fmt.Errorf("unauthorized to view this section")
	}

	return s.toSectionResponse(section), nil
}

// ListSections lists all sections in a course
func (s *CourseService) ListSections(ctx context.Context, courseID int64, userID int64, role string) ([]*dto.SectionResponse, error) {
	// Check course permissions
	course, err := s.courseRepo.GetByID(ctx, courseID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("course not found")
		}
		return nil, fmt.Errorf("failed to get course: %w", err)
	}

	sections, err := s.courseRepo.ListSectionsByCourse(ctx, courseID)
	if err != nil {
		return nil, fmt.Errorf("failed to list sections: %w", err)
	}

	// Check if student is enrolled (for viewing unpublished sections)
	isEnrolled := false
	if role == models.RoleStudent {
		enrollment, _ := s.enrollmentRepo.GetByStudentAndCourse(ctx, userID, courseID)
		isEnrolled = enrollment != nil && enrollment.Status == models.EnrollmentAccepted
	}

	result := make([]*dto.SectionResponse, 0, len(sections))
	for _, section := range sections {
		// Allow viewing if:
		// 1. Section is published, OR
		// 2. User is course creator/admin, OR
		// 3. Student is enrolled in the course
		if !section.IsPublished {
			if role == models.RoleAdmin || course.CreatedBy == userID || (role == models.RoleStudent && isEnrolled) {
				result = append(result, s.toSectionResponse(section))
			}
		} else {
			result = append(result, s.toSectionResponse(section))
		}
	}

	return result, nil
}

// UpdateSection updates a section
func (s *CourseService) UpdateSection(ctx context.Context, sectionID int64, req *dto.UpdateSectionRequest, userID int64, role string) error {
	section, err := s.courseRepo.GetSectionByID(ctx, sectionID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("section not found")
		}
		return fmt.Errorf("failed to get section: %w", err)
	}

	// Check permissions
	course, err := s.courseRepo.GetByID(ctx, section.CourseID)
	if err != nil {
		return fmt.Errorf("failed to get course: %w", err)
	}

	if role != models.RoleAdmin && course.CreatedBy != userID {
		return fmt.Errorf("unauthorized to update this section")
	}

	// Build updates
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

	return s.courseRepo.UpdateSection(ctx, sectionID, updates)
}

// DeleteSection deletes a section
func (s *CourseService) DeleteSection(ctx context.Context, sectionID int64, userID int64, role string) error {
	section, err := s.courseRepo.GetSectionByID(ctx, sectionID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("section not found")
		}
		return fmt.Errorf("failed to get section: %w", err)
	}

	// Check permissions
	course, err := s.courseRepo.GetByID(ctx, section.CourseID)
	if err != nil {
		return fmt.Errorf("failed to get course: %w", err)
	}

	if role != models.RoleAdmin && course.CreatedBy != userID {
		return fmt.Errorf("unauthorized to delete this section")
	}

	return s.courseRepo.DeleteSection(ctx, sectionID)
}

// ===== CONTENT METHODS =====

// CreateContent creates new content in a section
func (s *CourseService) CreateContent(ctx context.Context, sectionID int64, req *dto.CreateContentRequest, userID int64, role string) (*dto.ContentResponse, error) {
	section, err := s.courseRepo.GetSectionByID(ctx, sectionID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("section not found")
		}
		return nil, fmt.Errorf("failed to get section: %w", err)
	}

	// Check permissions
	course, err := s.courseRepo.GetByID(ctx, section.CourseID)
	if err != nil {
		return nil, fmt.Errorf("failed to get course: %w", err)
	}

	if role != models.RoleAdmin && course.CreatedBy != userID {
		return nil, fmt.Errorf("unauthorized to create content in this section")
	}

	// Convert metadata to JSON
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

	created, err := s.courseRepo.CreateContent(ctx, content)
	if err != nil {
		return nil, fmt.Errorf("failed to create content: %w", err)
	}

	return s.toContentResponse(created)
}

// GetContent retrieves content by ID
func (s *CourseService) GetContent(ctx context.Context, contentID int64, userID int64, role string) (*dto.ContentResponse, error) {
	content, err := s.courseRepo.GetContentByID(ctx, contentID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("content not found")
		}
		return nil, fmt.Errorf("failed to get content: %w", err)
	}

	// Check permissions
	section, err := s.courseRepo.GetSectionByID(ctx, content.SectionID)
	if err != nil {
		return nil, fmt.Errorf("failed to get section: %w", err)
	}

	course, err := s.courseRepo.GetByID(ctx, section.CourseID)
	if err != nil {
		return nil, fmt.Errorf("failed to get course: %w", err)
	}

	if !content.IsPublished && role != models.RoleAdmin && course.CreatedBy != userID {
		return nil, fmt.Errorf("unauthorized to view this content")
	}

	return s.toContentResponse(content)
}

// ListContent lists all content in a section
func (s *CourseService) ListContent(ctx context.Context, sectionID int64, userID int64, role string) ([]*dto.ContentResponse, error) {
	section, err := s.courseRepo.GetSectionByID(ctx, sectionID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("section not found")
		}
		return nil, fmt.Errorf("failed to get section: %w", err)
	}

	course, err := s.courseRepo.GetByID(ctx, section.CourseID)
	if err != nil {
		return nil, fmt.Errorf("failed to get course: %w", err)
	}

	contents, err := s.courseRepo.ListContentBySection(ctx, sectionID)
	if err != nil {
		return nil, fmt.Errorf("failed to list content: %w", err)
	}

	// Check if student is enrolled (for viewing unpublished content)
	isEnrolled := false
	if role == models.RoleStudent {
		enrollment, _ := s.enrollmentRepo.GetByStudentAndCourse(ctx, userID, course.ID)
		isEnrolled = enrollment != nil && enrollment.Status == models.EnrollmentAccepted
	}

	result := make([]*dto.ContentResponse, 0, len(contents))
	for _, content := range contents {
		// Allow viewing if:
		// 1. Content is published, OR
		// 2. User is course creator/admin, OR
		// 3. Student is enrolled in the course
		if !content.IsPublished {
			if role == models.RoleAdmin || course.CreatedBy == userID || (role == models.RoleStudent && isEnrolled) {
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

// UpdateContent updates content
func (s *CourseService) UpdateContent(ctx context.Context, contentID int64, req *dto.UpdateContentRequest, userID int64, role string) error {
	content, err := s.courseRepo.GetContentByID(ctx, contentID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("content not found")
		}
		return fmt.Errorf("failed to get content: %w", err)
	}

	// Check permissions
	section, err := s.courseRepo.GetSectionByID(ctx, content.SectionID)
	if err != nil {
		return fmt.Errorf("failed to get section: %w", err)
	}

	course, err := s.courseRepo.GetByID(ctx, section.CourseID)
	if err != nil {
		return fmt.Errorf("failed to get course: %w", err)
	}

	if role != models.RoleAdmin && course.CreatedBy != userID {
		return fmt.Errorf("unauthorized to update this content")
	}

	// Build updates
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

	if len(updates) == 0 {
		return fmt.Errorf("no fields to update")
	}

	return s.courseRepo.UpdateContent(ctx, contentID, updates)
}

// DeleteContent deletes content
func (s *CourseService) DeleteContent(ctx context.Context, contentID int64, userID int64, role string) error {
	content, err := s.courseRepo.GetContentByID(ctx, contentID)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("content not found")
		}
		return fmt.Errorf("failed to get content: %w", err)
	}

	// Check permissions
	section, err := s.courseRepo.GetSectionByID(ctx, content.SectionID)
	if err != nil {
		return fmt.Errorf("failed to get section: %w", err)
	}

	course, err := s.courseRepo.GetByID(ctx, section.CourseID)
	if err != nil {
		return fmt.Errorf("failed to get course: %w", err)
	}

	if role != models.RoleAdmin && course.CreatedBy != userID {
		return fmt.Errorf("unauthorized to delete this content")
	}

	return s.courseRepo.DeleteContent(ctx, contentID)
}

// Helper functions

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

	// Parse metadata
	if len(content.Metadata) > 0 {
		var metadata map[string]interface{}
		if err := json.Unmarshal(content.Metadata, &metadata); err == nil {
			resp.Metadata = metadata
		}
	}

	return resp, nil
}
