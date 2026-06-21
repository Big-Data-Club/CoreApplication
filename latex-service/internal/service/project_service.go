package service

import (
	"bytes"
	"context"
	"errors"
	"fmt"

	"latex-service/internal/dto"
	"latex-service/internal/repository"
)

// ProjectService manages LaTeX projects
type ProjectService struct {
	projectRepo *repository.ProjectRepository
	fileService *FileService
	accessSvc   *AccessService
}

// NewProjectService creates a new ProjectService
func NewProjectService(projectRepo *repository.ProjectRepository, fileService *FileService, accessSvc *AccessService) *ProjectService {
	return &ProjectService{
		projectRepo: projectRepo,
		fileService: fileService,
		accessSvc:   accessSvc,
	}
}

// CreateProject creates a project and seeds a default main.tex if no template is specified
func (s *ProjectService) CreateProject(ctx context.Context, req *dto.CreateProjectRequest, userID int64) (*dto.ProjectResponse, error) {
	p, err := s.projectRepo.Create(ctx, req, userID)
	if err != nil {
		return nil, err
	}

	// Seed default main.tex if no template
	if req.TemplateID == "" {
		defaultContent := `\documentclass{article}
\begin{document}
\title{` + p.Title + `}
\author{User ` + fmt.Sprintf("%d", userID) + `}
\date{\today}
\maketitle

\section{Introduction}
Welcome to your new BDCTex project!

\end{document}
`
		buf := bytes.NewBufferString(defaultContent)
		_, err = s.fileService.UploadFile(ctx, userID, p.ID, "main.tex", buf, int64(buf.Len()), "text/plain")
		if err != nil {
			// Log but don't fail project creation
		}
	}

	p.UserRole = "owner"
	return p, nil
}

// GetProject retrieves a project's details. Resolves the caller's access level.
func (s *ProjectService) GetProject(ctx context.Context, id int64, userID int64) (*dto.ProjectResponse, error) {
	level, err := s.accessSvc.CheckAccess(ctx, id, userID)
	if err != nil {
		return nil, err
	}
	if level == AccessNone {
		return nil, errors.New("project not found or access denied")
	}

	p, err := s.projectRepo.GetByIDRaw(ctx, id)
	if err != nil {
		return nil, err
	}
	p.UserRole = level.String()
	return p, nil
}

// ListProjects lists all projects the user owns OR has been shared with, with pagination.
func (s *ProjectService) ListProjects(ctx context.Context, userID int64, limit, offset int) ([]*dto.ProjectResponse, int, error) {
	return s.projectRepo.ListAccessibleByUser(ctx, userID, limit, offset)
}

// UpdateProject updates a project's metadata. Requires Editor+ access.
func (s *ProjectService) UpdateProject(ctx context.Context, id int64, userID int64, req *dto.UpdateProjectRequest) (*dto.ProjectResponse, error) {
	if err := s.accessSvc.RequireAtLeast(ctx, id, userID, AccessEditor); err != nil {
		return nil, err
	}
	return s.projectRepo.Update(ctx, id, userID, req)
}

// DeleteProject soft-deletes a project. Only the owner may delete.
func (s *ProjectService) DeleteProject(ctx context.Context, id int64, userID int64) error {
	if err := s.accessSvc.RequireAtLeast(ctx, id, userID, AccessOwner); err != nil {
		return err
	}
	return s.projectRepo.Delete(ctx, id, userID)
}
