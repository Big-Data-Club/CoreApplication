package service

import (
	"context"
	"fmt"
	"strings"
	"sync"

	"golang.org/x/sync/errgroup"

	"example/hello/internal/dto"
	"example/hello/internal/repository"
	"example/hello/pkg/cache"
	"example/hello/pkg/logger"
)

// UserSyncService propagates user/role state from the auth service into LMS.
// It holds a *cache.RedisCache so role changes invalidate the cached
// /me/roles answer immediately — without this, freshly granted roles would
// take up to userRolesTTL to become effective.
type UserSyncService struct {
	userRepo *repository.UserRepository
	cache    *cache.RedisCache
}

func NewUserSyncService(userRepo *repository.UserRepository, c *cache.RedisCache) *UserSyncService {
	return &UserSyncService{
		userRepo: userRepo,
		cache:    c,
	}
}

// SyncUser synchronizes a single user from auth service.
// Only roles with source='sync' are replaced; source='manual' roles are preserved.
func (s *UserSyncService) SyncUser(ctx context.Context, req *dto.UserSyncRequest) (*dto.UserSyncResponse, error) {
	// Get or create user
	user, err := s.userRepo.GetOrCreateUser(ctx, req.UserID, req.Email, req.FullName, req.Org)
	if err != nil {
		logger.Error(fmt.Sprintf("Failed to get/create user %s", req.Email), err)
		return nil, fmt.Errorf("failed to sync user: %w", err)
	}

	isNew := user.CreatedAt.Equal(user.UpdatedAt)

	// Update full name if changed
	if user.FullName != req.FullName {
		if err := s.userRepo.UpdateFullName(ctx, req.UserID, req.FullName); err != nil {
			logger.Error(fmt.Sprintf("Failed to update full name for user %s", req.Email), err)
		}
	}

	// Update organization if changed
	if user.Organization != req.Org {
		if err := s.userRepo.UpdateOrganization(ctx, req.UserID, req.Org); err != nil {
			logger.Error(fmt.Sprintf("Failed to update organization for user %s", req.Email), err)
		}
	}

	// Auto-associate user with organization in LMS organization_members if organization exists
	if req.Org != "" {
		if err := s.userRepo.AssociateUserWithOrganization(ctx, req.UserID, req.Org); err != nil {
			logger.Error(fmt.Sprintf("Failed to auto-associate user with org %s", req.Org), err)
		}
	}

	// Clear only synced roles (preserve manually assigned ones)
	if err := s.userRepo.ClearSyncedRoles(ctx, req.UserID); err != nil {
		return nil, fmt.Errorf("failed to clear synced roles: %w", err)
	}

	// Add new synced roles
	rolesAssigned := []string{}
	for _, role := range req.Roles {
		if !isValidRole(role) {
			logger.Warn(fmt.Sprintf("Empty role skipped for user %s", req.Email))
			continue
		}

		if err := s.userRepo.AddRoleWithSource(ctx, req.UserID, role, "sync"); err != nil {
			logger.Error(fmt.Sprintf("Failed to add role %s to user %s", role, req.Email), err)
			continue
		}
		rolesAssigned = append(rolesAssigned, role)
	}

	logger.Info(fmt.Sprintf("Synced user %s with roles: %v", req.Email, rolesAssigned))

	// Roles changed — drop the cached /me/roles answer so the next request
	// reflects the new state instead of waiting for the TTL.
	if s.cache != nil {
		cache.Invalidate(ctx, s.cache, cache.KeyUserRoles(req.UserID))
	}

	return &dto.UserSyncResponse{
		UserID:        user.ID,
		Email:         user.Email,
		RolesAssigned: rolesAssigned,
		IsNew:         isNew,
	}, nil
}

// BulkSyncUsers synchronizes multiple users from auth service
func (s *UserSyncService) BulkSyncUsers(ctx context.Context, req *dto.BulkUserSyncRequest) (*dto.BulkUserSyncResponse, error) {
	response := &dto.BulkUserSyncResponse{
		TotalUsers:   len(req.Users),
		SuccessCount: 0,
		FailedCount:  0,
		SuccessUsers: []dto.UserSyncResponse{},
		FailedUsers:  []dto.SyncError{},
	}

	var mu sync.Mutex

	g, gCtx := errgroup.WithContext(ctx)
	g.SetLimit(15)

	for i := range req.Users {
		userReq := req.Users[i]
		g.Go(func() error {
			syncResp, err := s.SyncUser(gCtx, &userReq)

			mu.Lock()
			defer mu.Unlock()

			if err != nil {
				response.FailedCount++
				response.FailedUsers = append(response.FailedUsers, dto.SyncError{
					UserID: userReq.UserID,
					Email:  userReq.Email,
					Error:  err.Error(),
				})
				logger.Error(fmt.Sprintf("Failed to sync user %s", userReq.Email), err)
			} else {
				response.SuccessCount++
				response.SuccessUsers = append(response.SuccessUsers, *syncResp)
			}
			return nil
		})
	}
	g.Wait()

	logger.Info(fmt.Sprintf("Bulk sync completed: %d success, %d failed out of %d total",
		response.SuccessCount, response.FailedCount, response.TotalUsers))

	return response, nil
}

// DeleteUser removes user from LMS
func (s *UserSyncService) DeleteUser(ctx context.Context, userID int64) error {
	if err := s.userRepo.ClearUserRoles(ctx, userID); err != nil {
		return fmt.Errorf("failed to clear user roles: %w", err)
	}

	if s.cache != nil {
		cache.Invalidate(ctx, s.cache, cache.KeyUserRoles(userID))
	}
	logger.Info(fmt.Sprintf("Removed all roles from user %d", userID))

	return nil
}

// isValidRole accepts any non-empty role string (dynamic RBAC).
func isValidRole(role string) bool {
	return strings.TrimSpace(role) != ""
}