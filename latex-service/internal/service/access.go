package service

import (
	"context"
	"errors"

	"latex-service/internal/repository"
)

// AccessLevel represents the permission level a user has for a project
type AccessLevel int

const (
	AccessNone     AccessLevel = 0
	AccessViewer   AccessLevel = 1
	AccessReviewer AccessLevel = 2
	AccessEditor   AccessLevel = 3
	AccessOwner    AccessLevel = 4
)

// String returns the string representation of an AccessLevel
func (a AccessLevel) String() string {
	switch a {
	case AccessOwner:
		return "owner"
	case AccessEditor:
		return "editor"
	case AccessReviewer:
		return "reviewer"
	case AccessViewer:
		return "viewer"
	default:
		return "none"
	}
}

// AccessLevelFromString converts a role string to an AccessLevel
func AccessLevelFromString(role string) AccessLevel {
	switch role {
	case "owner":
		return AccessOwner
	case "editor":
		return AccessEditor
	case "reviewer":
		return AccessReviewer
	case "viewer":
		return AccessViewer
	default:
		return AccessNone
	}
}

// AccessService is the central access-control layer used by all services
type AccessService struct {
	projectRepo *repository.ProjectRepository
	collabRepo  *repository.CollaboratorRepository
}

// NewAccessService creates a new AccessService
func NewAccessService(projectRepo *repository.ProjectRepository, collabRepo *repository.CollaboratorRepository) *AccessService {
	return &AccessService{
		projectRepo: projectRepo,
		collabRepo:  collabRepo,
	}
}

// CheckAccess returns the user's access level for a project.
// Resolution order: owner → collaborator role → none
func (s *AccessService) CheckAccess(ctx context.Context, projectID int64, userID int64) (AccessLevel, error) {
	// 1. Check ownership
	p, err := s.projectRepo.GetByIDRaw(ctx, projectID)
	if err != nil {
		return AccessNone, err
	}
	if p.UserID == userID {
		return AccessOwner, nil
	}

	// 2. Check collaborator table
	collab, err := s.collabRepo.GetByProjectAndUser(ctx, projectID, userID)
	if err == nil && collab != nil {
		return AccessLevelFromString(collab.Role), nil
	}

	return AccessNone, nil
}

// RequireAtLeast checks that the user has at least the given access level.
// Returns a descriptive error if the check fails.
func (s *AccessService) RequireAtLeast(ctx context.Context, projectID int64, userID int64, minLevel AccessLevel) error {
	level, err := s.CheckAccess(ctx, projectID, userID)
	if err != nil {
		return err
	}
	if level < minLevel {
		if level == AccessNone {
			return errors.New("project not found or access denied")
		}
		return errors.New("insufficient permissions for this operation")
	}
	return nil
}

// IsOwner returns true only if the user is the project owner
func (s *AccessService) IsOwner(ctx context.Context, projectID int64, userID int64) (bool, error) {
	level, err := s.CheckAccess(ctx, projectID, userID)
	if err != nil {
		return false, err
	}
	return level == AccessOwner, nil
}
