package service

import (
	"context"
	"fmt"
	"sync"

	"golang.org/x/sync/errgroup"

	"example/hello/internal/dto"
	"example/hello/internal/models"
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

// SyncUser synchronizes a single user from auth service
func (s *UserSyncService) SyncUser(ctx context.Context, req *dto.UserSyncRequest) (*dto.UserSyncResponse, error) {
	// Get or create user
	user, err := s.userRepo.GetOrCreateUser(ctx, req.UserID, req.Email, req.FullName)
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

	// Sync roles - xóa roles cũ và thêm roles mới
	existingRoles, err := s.userRepo.GetUserRoles(ctx, req.UserID)
	if err != nil {
		return nil, fmt.Errorf("failed to get existing roles: %w", err)
	}

	// Xóa roles không còn trong danh sách mới
	for _, existingRole := range existingRoles {
		found := false
		for _, newRole := range req.Roles {
			if existingRole == newRole {
				found = true
				break
			}
		}
		if !found {
			if err := s.userRepo.RemoveRole(ctx, req.UserID, existingRole); err != nil {
				logger.Error(fmt.Sprintf("Failed to remove role %s from user %s", existingRole, req.Email), err)
			}
		}
	}

	// Thêm roles mới
	rolesAssigned := []string{}
	for _, role := range req.Roles {
		// Validate role
		if !isValidRole(role) {
			logger.Warn(fmt.Sprintf("Invalid role %s for user %s", role, req.Email))
			continue
		}

		if err := s.userRepo.AddRole(ctx, req.UserID, role); err != nil {
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
	// First remove all roles
	roles, err := s.userRepo.GetUserRoles(ctx, userID)
	if err != nil {
		return fmt.Errorf("failed to get user roles: %w", err)
	}

	for _, role := range roles {
		if err := s.userRepo.RemoveRole(ctx, userID, role); err != nil {
			logger.Error(fmt.Sprintf("Failed to remove role %s from user %d", role, userID), err)
		}
	}

	// Note: We don't actually delete the user record to maintain referential integrity
	// Just removing all roles effectively "deactivates" them from LMS perspective
	if s.cache != nil {
		cache.Invalidate(ctx, s.cache, cache.KeyUserRoles(userID))
	}
	logger.Info(fmt.Sprintf("Removed all roles from user %d", userID))

	return nil
}

// isValidRole validates if a role is allowed in LMS
func isValidRole(role string) bool {
	validRoles := []string{
		models.RoleStudent,
		models.RoleTeacher,
		models.RoleAdmin,
	}

	for _, validRole := range validRoles {
		if role == validRole {
			return true
		}
	}

	return false
}