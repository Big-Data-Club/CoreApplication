package service

import (
	"context"
	"errors"

	"latex-service/internal/dto"
	"latex-service/internal/repository"
	"latex-service/pkg/auth"
)

// CollaboratorService manages project collaborators
type CollaboratorService struct {
	collabRepo  *repository.CollaboratorRepository
	projectRepo *repository.ProjectRepository
	accessSvc   *AccessService
	authClient  *auth.AuthClient
}

// NewCollaboratorService creates a new CollaboratorService
func NewCollaboratorService(
	collabRepo *repository.CollaboratorRepository,
	projectRepo *repository.ProjectRepository,
	accessSvc *AccessService,
	authClient *auth.AuthClient,
) *CollaboratorService {
	return &CollaboratorService{
		collabRepo:  collabRepo,
		projectRepo: projectRepo,
		accessSvc:   accessSvc,
		authClient:  authClient,
	}
}

// AddCollaborator adds a user as collaborator. Only the owner may call this.
func (s *CollaboratorService) AddCollaborator(ctx context.Context, projectID, ownerUserID int64, req *dto.AddCollaboratorRequest) (*dto.CollaboratorResponse, error) {
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, ownerUserID, AccessOwner); err != nil {
		return nil, err
	}

	// Look up user by email in auth service
	userInfo, err := s.authClient.LookupUserByEmail(ctx, req.Email)
	if err != nil {
		return nil, err
	}

	// Prevent owner from adding themselves
	if userInfo.ID == ownerUserID {
		return nil, errors.New("cannot add the project owner as a collaborator")
	}

	collab, err := s.collabRepo.Add(ctx, projectID, userInfo.ID, userInfo.Email, req.Role, ownerUserID)
	if err != nil {
		return nil, err
	}
	return collab, nil
}

// RemoveCollaborator removes a collaborator. Only the owner may call this.
func (s *CollaboratorService) RemoveCollaborator(ctx context.Context, projectID, ownerUserID, targetUserID int64) error {
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, ownerUserID, AccessOwner); err != nil {
		return err
	}
	return s.collabRepo.Remove(ctx, projectID, targetUserID)
}

// UpdateRole changes a collaborator's role. Only the owner may call this.
func (s *CollaboratorService) UpdateRole(ctx context.Context, projectID, ownerUserID, targetUserID int64, newRole string) (*dto.CollaboratorResponse, error) {
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, ownerUserID, AccessOwner); err != nil {
		return nil, err
	}
	return s.collabRepo.UpdateRole(ctx, projectID, targetUserID, newRole)
}

// ListCollaborators returns all collaborators. Any project member may call this.
func (s *CollaboratorService) ListCollaborators(ctx context.Context, projectID, userID int64) ([]*dto.CollaboratorResponse, error) {
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessViewer); err != nil {
		return nil, err
	}
	return s.collabRepo.ListByProject(ctx, projectID)
}
