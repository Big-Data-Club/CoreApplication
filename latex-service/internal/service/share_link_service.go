package service

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"

	"latex-service/internal/dto"
	"latex-service/internal/repository"
)

// ShareLinkService manages project share links
type ShareLinkService struct {
	linkRepo    *repository.ShareLinkRepository
	collabRepo  *repository.CollaboratorRepository
	accessSvc   *AccessService
	frontendURL string // e.g. https://bdc.hpcc.vn for building the join URL
}

// NewShareLinkService creates a new ShareLinkService
func NewShareLinkService(
	linkRepo *repository.ShareLinkRepository,
	collabRepo *repository.CollaboratorRepository,
	accessSvc *AccessService,
	frontendURL string,
) *ShareLinkService {
	return &ShareLinkService{
		linkRepo:    linkRepo,
		collabRepo:  collabRepo,
		accessSvc:   accessSvc,
		frontendURL: frontendURL,
	}
}

// CreateLink creates a new share link. Owner or Editor may create links.
func (s *ShareLinkService) CreateLink(ctx context.Context, projectID, userID int64, req *dto.CreateShareLinkRequest) (*dto.ShareLinkResponse, error) {
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessEditor); err != nil {
		return nil, err
	}

	token, err := generateToken(32)
	if err != nil {
		return nil, fmt.Errorf("failed to generate share token: %w", err)
	}

	link, err := s.linkRepo.Create(ctx, projectID, token, req.Role, userID, nil)
	if err != nil {
		return nil, err
	}
	link.URL = s.buildURL(link.Token)
	return link, nil
}

// ListLinks lists all share links for a project. Owner or Editor may view links.
func (s *ShareLinkService) ListLinks(ctx context.Context, projectID, userID int64) ([]*dto.ShareLinkResponse, error) {
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessEditor); err != nil {
		return nil, err
	}
	links, err := s.linkRepo.ListByProject(ctx, projectID)
	if err != nil {
		return nil, err
	}
	for _, l := range links {
		l.URL = s.buildURL(l.Token)
	}
	return links, nil
}

// DeactivateLink deactivates a share link. Owner or Editor may deactivate links.
func (s *ShareLinkService) DeactivateLink(ctx context.Context, linkID, projectID, userID int64) error {
	if err := s.accessSvc.RequireAtLeast(ctx, projectID, userID, AccessEditor); err != nil {
		return err
	}
	return s.linkRepo.Deactivate(ctx, linkID)
}

// JoinViaLink adds the user as a collaborator using the link's role.
// If the user is already owner or collaborator, it is a no-op / role update.
func (s *ShareLinkService) JoinViaLink(ctx context.Context, token string, userID int64, userEmail string) (*dto.ShareLinkResponse, error) {
	link, err := s.linkRepo.GetByToken(ctx, token)
	if err != nil {
		return nil, err
	}

	// Check if user is already owner
	level, err := s.accessSvc.CheckAccess(ctx, link.ProjectID, userID)
	if err != nil {
		return nil, err
	}
	if level == AccessOwner {
		link.URL = s.buildURL(link.Token)
		return link, nil // owner needs no collaborator entry
	}

	// Add or update collaborator role
	_, err = s.collabRepo.Add(ctx, link.ProjectID, userID, userEmail, link.Role, 0)
	if err != nil {
		// If already collaborator, try updating the role instead
		_, updateErr := s.collabRepo.UpdateRole(ctx, link.ProjectID, userID, link.Role)
		if updateErr != nil {
			return nil, err
		}
	}

	link.URL = s.buildURL(link.Token)
	return link, nil
}

func (s *ShareLinkService) buildURL(token string) string {
	return fmt.Sprintf("%s/bdctex/join/%s", s.frontendURL, token)
}

func generateToken(length int) (string, error) {
	b := make([]byte, length)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}
