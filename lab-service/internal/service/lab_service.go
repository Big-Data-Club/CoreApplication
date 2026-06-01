package service

import (
	"context"
	"database/sql"
	"fmt"
	"net/http"

	"lab-service/internal/dto"
	"lab-service/internal/repository"
)

type LabService struct {
	labRepo        *repository.LabRepository
	enrollmentRepo *repository.EnrollmentRepository
}

func NewLabService(labRepo *repository.LabRepository, enrollmentRepo *repository.EnrollmentRepository) *LabService {
	return &LabService{labRepo: labRepo, enrollmentRepo: enrollmentRepo}
}

func (s *LabService) CreateLab(ctx context.Context, req *dto.CreateLabRequest, userID int64) (*dto.LabResponse, int, error) {
	lab, err := s.labRepo.Create(ctx, req, userID)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("failed to create lab: %w", err)
	}
	return lab, http.StatusCreated, nil
}

func (s *LabService) GetLab(ctx context.Context, labID int64) (*dto.LabResponse, int, error) {
	lab, err := s.labRepo.GetByID(ctx, labID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, http.StatusNotFound, fmt.Errorf("lab not found")
		}
		return nil, http.StatusInternalServerError, fmt.Errorf("failed to get lab: %w", err)
	}
	return lab, http.StatusOK, nil
}

func (s *LabService) ListPublishedLabs(ctx context.Context, labType, category, level, search string, page, pageSize int) (*dto.ListResponse, int, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize

	labs, total, err := s.labRepo.ListPublished(ctx, labType, category, level, search, pageSize, offset)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("failed to list labs: %w", err)
	}
	if labs == nil {
		labs = []dto.LabResponse{}
	}
	return dto.NewListResponse(labs, page, pageSize, total), http.StatusOK, nil
}

func (s *LabService) ListMyLabs(ctx context.Context, userID int64, status string, page, pageSize int) (*dto.ListResponse, int, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize

	labs, total, err := s.labRepo.ListByCreator(ctx, userID, status, pageSize, offset)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("failed to list labs: %w", err)
	}
	if labs == nil {
		labs = []dto.LabResponse{}
	}
	return dto.NewListResponse(labs, page, pageSize, total), http.StatusOK, nil
}

func (s *LabService) UpdateLab(ctx context.Context, labID int64, req *dto.UpdateLabRequest, userID int64, userRole string) (int, error) {
	if err := s.checkOwnership(ctx, labID, userID, userRole); err != nil {
		return http.StatusForbidden, err
	}
	if err := s.labRepo.Update(ctx, labID, req); err != nil {
		return http.StatusInternalServerError, fmt.Errorf("failed to update lab: %w", err)
	}
	return http.StatusOK, nil
}

func (s *LabService) DeleteLab(ctx context.Context, labID int64, userID int64, userRole string) (int, error) {
	if err := s.checkOwnership(ctx, labID, userID, userRole); err != nil {
		return http.StatusForbidden, err
	}
	if err := s.labRepo.Delete(ctx, labID); err != nil {
		return http.StatusInternalServerError, fmt.Errorf("failed to delete lab: %w", err)
	}
	return http.StatusOK, nil
}

func (s *LabService) PublishLab(ctx context.Context, labID int64, userID int64, userRole string) (int, error) {
	if err := s.checkOwnership(ctx, labID, userID, userRole); err != nil {
		return http.StatusForbidden, err
	}
	if err := s.labRepo.Publish(ctx, labID); err != nil {
		return http.StatusInternalServerError, fmt.Errorf("failed to publish lab: %w", err)
	}
	return http.StatusOK, nil
}

// ── Sections ────────────────────────────────────────────────────

func (s *LabService) CreateSection(ctx context.Context, labID int64, req *dto.CreateSectionRequest, userID int64, userRole string) (*dto.SectionResponse, int, error) {
	if err := s.checkOwnership(ctx, labID, userID, userRole); err != nil {
		return nil, http.StatusForbidden, err
	}
	sec, err := s.labRepo.CreateSection(ctx, labID, req)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("failed to create section: %w", err)
	}
	return sec, http.StatusCreated, nil
}

func (s *LabService) ListSections(ctx context.Context, labID int64) ([]dto.SectionResponse, int, error) {
	sections, err := s.labRepo.ListSections(ctx, labID)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("failed to list sections: %w", err)
	}
	if sections == nil {
		sections = []dto.SectionResponse{}
	}
	return sections, http.StatusOK, nil
}

func (s *LabService) UpdateSection(ctx context.Context, sectionID int64, req *dto.UpdateSectionRequest) (int, error) {
	if err := s.labRepo.UpdateSection(ctx, sectionID, req); err != nil {
		return http.StatusInternalServerError, fmt.Errorf("failed to update section: %w", err)
	}
	return http.StatusOK, nil
}

func (s *LabService) DeleteSection(ctx context.Context, sectionID int64) (int, error) {
	if err := s.labRepo.DeleteSection(ctx, sectionID); err != nil {
		return http.StatusInternalServerError, fmt.Errorf("failed to delete section: %w", err)
	}
	return http.StatusOK, nil
}

// ── Content ─────────────────────────────────────────────────────

func (s *LabService) CreateContent(ctx context.Context, sectionID int64, req *dto.CreateContentRequest, userID int64) (*dto.ContentResponse, int, error) {
	content, err := s.labRepo.CreateContent(ctx, sectionID, req, userID)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("failed to create content: %w", err)
	}
	return content, http.StatusCreated, nil
}

func (s *LabService) ListContent(ctx context.Context, sectionID int64) ([]dto.ContentResponse, int, error) {
	contents, err := s.labRepo.ListContent(ctx, sectionID)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("failed to list content: %w", err)
	}
	if contents == nil {
		contents = []dto.ContentResponse{}
	}
	return contents, http.StatusOK, nil
}

func (s *LabService) UpdateContent(ctx context.Context, contentID int64, req *dto.UpdateContentRequest) (int, error) {
	if err := s.labRepo.UpdateContent(ctx, contentID, req); err != nil {
		return http.StatusInternalServerError, fmt.Errorf("failed to update content: %w", err)
	}
	return http.StatusOK, nil
}

func (s *LabService) DeleteContent(ctx context.Context, contentID int64) (int, error) {
	if err := s.labRepo.DeleteContent(ctx, contentID); err != nil {
		return http.StatusInternalServerError, fmt.Errorf("failed to delete content: %w", err)
	}
	return http.StatusOK, nil
}


// ── Helpers ─────────────────────────────────────────────────────

func (s *LabService) checkOwnership(ctx context.Context, labID int64, userID int64, userRole string) error {
	if userRole == "ADMIN" {
		return nil
	}
	creatorID, err := s.labRepo.GetCreatorID(ctx, labID)
	if err != nil {
		return fmt.Errorf("lab not found")
	}
	if creatorID != userID {
		return fmt.Errorf("you don't have permission to modify this lab")
	}
	return nil
}
