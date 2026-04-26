package service

import (
	"context"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/repository"
	"example/hello/pkg/cache"
)

// userRolesTTL: roles change very rarely (admin grants), so a short cache
// window is enough to dramatically reduce DB load during a stampede on the
// /me/roles endpoint without making role revocation feel slow.
const userRolesTTL = 5 * time.Minute

type UserService struct {
	userRepo *repository.UserRepository
	cache    *cache.RedisCache
	loader   *cache.Loader
}

func NewUserService(userRepo *repository.UserRepository, c *cache.RedisCache) *UserService {
	return &UserService{
		userRepo: userRepo,
		cache:    c,
		loader:   cache.NewLoader(c),
	}
}

// GetMyRoles retrieves the roles for the authenticated user.
//
// Roles are looked up on most authenticated requests by clients that gate UI
// elements off the response. Caching keeps that hot path off the database.
// Invalidation happens in the user-sync service when the auth service pushes
// a role change.
func (s *UserService) GetMyRoles(ctx context.Context, userID int64, email string) (*dto.UserRolesResponse, error) {
	// Ensure user exists in database (fast path: this normally hits the row
	// inserted by the user-sync flow on first login).
	if _, err := s.userRepo.GetOrCreateUser(ctx, userID, email, ""); err != nil {
		return nil, err
	}

	roles, err := cache.GetOrLoad(ctx, s.loader, cache.KeyUserRoles(userID), userRolesTTL,
		func(ctx context.Context) ([]string, error) {
			return s.userRepo.GetUserRoles(ctx, userID)
		})
	if err != nil {
		return nil, err
	}

	return &dto.UserRolesResponse{
		UserID: userID,
		Email:  email,
		Roles:  roles,
	}, nil
}

// InvalidateRoles drops the cached roles for a user. Called by the user-sync
// service after role mutations propagate from the auth service.
func (s *UserService) InvalidateRoles(ctx context.Context, userID int64) {
	cache.Invalidate(ctx, s.cache, cache.KeyUserRoles(userID))
}