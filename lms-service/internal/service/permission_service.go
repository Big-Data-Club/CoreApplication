package service

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/cache"
	"example/hello/pkg/logger"
)

const (
	permCachePrefix = "perm:role:"
	permCacheTTL    = 10 * time.Minute
)

// PermissionService handles permission logic with Redis-backed caching.
type PermissionService struct {
	repo  *repository.PermissionRepository
	cache *cache.RedisCache
}

func NewPermissionService(repo *repository.PermissionRepository, cache *cache.RedisCache) *PermissionService {
	return &PermissionService{repo: repo, cache: cache}
}

// ListAll returns every permission (master data for UI).
func (s *PermissionService) ListAll(ctx context.Context) ([]dto.PermissionResponse, error) {
	perms, err := s.repo.FindAll(ctx)
	if err != nil {
		return nil, err
	}
	return toPermissionResponses(perms), nil
}

// GetRolePermissions returns the permissions currently assigned to a role.
func (s *PermissionService) GetRolePermissions(ctx context.Context, roleID int64) (*dto.RolePermissionsResponse, error) {
	// Single JOIN query — gets role name + permissions without a second roundtrip
	roleName, perms, err := s.repo.FindByRoleID(ctx, roleID)
	if err != nil {
		return nil, err
	}
	return &dto.RolePermissionsResponse{
		RoleID:      roleID,
		RoleName:    roleName,
		Permissions: toPermissionResponses(perms),
	}, nil
}

// AssignPermissions replaces the permission set for a role and invalidates cache.
func (s *PermissionService) AssignPermissions(ctx context.Context, roleID int64, permIDs []int64) error {
	// Get role name for cache invalidation (single query that also confirms role exists)
	roleName, _, err := s.repo.FindByRoleID(ctx, roleID)
	if err != nil {
		return fmt.Errorf("role not found: %w", err)
	}

	if err := s.repo.AssignToRole(ctx, roleID, permIDs); err != nil {
		return err
	}

	// Invalidate cache
	cacheKey := permCachePrefix + roleName
	if err := s.cache.Delete(ctx, cacheKey); err != nil {
		logger.Warn(fmt.Sprintf("Failed to invalidate permission cache for %s: %v", roleName, err))
	}

	return nil
}

// CheckPermission checks whether a role has a specific permission code.
// ADMIN always passes. Results are cached in Redis.
func (s *PermissionService) CheckPermission(ctx context.Context, roleName string, code string) (bool, error) {
	// Super-admin bypass
	if roleName == "ADMIN" {
		return true, nil
	}

	codes, err := s.getCachedCodes(ctx, roleName)
	if err != nil {
		return false, err
	}

	for _, c := range codes {
		if c == code {
			return true, nil
		}
	}
	return false, nil
}

// getCachedCodes returns the permission codes for a role, using Redis as a
// read-through cache. On miss it queries the DB and populates the cache.
func (s *PermissionService) getCachedCodes(ctx context.Context, roleName string) ([]string, error) {
	cacheKey := permCachePrefix + roleName

	// Try cache first
	raw, err := s.cache.Get(ctx, cacheKey)
	if err == nil && raw != "" {
		var codes []string
		if jsonErr := json.Unmarshal([]byte(raw), &codes); jsonErr == nil {
			return codes, nil
		}
	}

	// Cache miss — query DB
	codes, err := s.repo.FindCodesByRoleName(ctx, roleName)
	if err != nil {
		return nil, err
	}
	if codes == nil {
		codes = []string{}
	}

	// Populate cache
	data, _ := json.Marshal(codes)
	if setErr := s.cache.Set(ctx, cacheKey, string(data), permCacheTTL); setErr != nil {
		logger.Warn(fmt.Sprintf("Failed to cache permissions for %s: %v", roleName, setErr))
	}

	return codes, nil
}

func toPermissionResponses(perms []models.Permission) []dto.PermissionResponse {
	out := make([]dto.PermissionResponse, len(perms))
	for i, p := range perms {
		out[i] = dto.PermissionResponse{
			ID:          p.ID,
			Code:        p.Code,
			Module:      p.Module,
			Description: p.Description,
		}
	}
	return out
}
