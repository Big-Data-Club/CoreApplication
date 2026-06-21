package service

import (
	"bytes"
	"context"
	"fmt"

	"latex-service/internal/dto"
	"latex-service/internal/repository"
)

type ProjectService struct {
	projectRepo *repository.ProjectRepository
	fileService *FileService
}

func NewProjectService(projectRepo *repository.ProjectRepository, fileService *FileService) *ProjectService {
	return &ProjectService{
		projectRepo: projectRepo,
		fileService: fileService,
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
			// We log but don't fail project creation
			// logger.Error("Failed to seed default main.tex", err)
		}
	}

	return p, nil
}

// GetProject retrieves a project's details
func (s *ProjectService) GetProject(ctx context.Context, id int64, userID int64) (*dto.ProjectResponse, error) {
	return s.projectRepo.GetByID(ctx, id, userID)
}

// ListProjects lists a user's active projects with pagination
func (s *ProjectService) ListProjects(ctx context.Context, userID int64, limit, offset int) ([]*dto.ProjectResponse, int, error) {
	return s.projectRepo.ListByUserID(ctx, userID, limit, offset)
}

// UpdateProject updates a project's metadata
func (s *ProjectService) UpdateProject(ctx context.Context, id int64, userID int64, req *dto.UpdateProjectRequest) (*dto.ProjectResponse, error) {
	return s.projectRepo.Update(ctx, id, userID, req)
}

// DeleteProject soft-deletes a project
func (s *ProjectService) DeleteProject(ctx context.Context, id int64, userID int64) error {
	return s.projectRepo.Delete(ctx, id, userID)
}
