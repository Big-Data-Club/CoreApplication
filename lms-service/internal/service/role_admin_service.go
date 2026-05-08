package service

import (
	"context"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/cache"
)

type RoleAdminService struct {
	roleDefRepo *repository.RoleDefinitionRepository
	userRepo    *repository.UserRepository
	cache       *cache.RedisCache
}

func NewRoleAdminService(roleDefRepo *repository.RoleDefinitionRepository, userRepo *repository.UserRepository, c *cache.RedisCache) *RoleAdminService {
	return &RoleAdminService{
		roleDefRepo: roleDefRepo,
		userRepo:    userRepo,
		cache:       c,
	}
}

func (s *RoleAdminService) ListRoles(ctx context.Context) ([]models.RoleDefinition, error) {
	return s.roleDefRepo.FindAll(ctx)
}

func (s *RoleAdminService) CreateRole(ctx context.Context, req *dto.RoleDefinitionRequest) (*models.RoleDefinition, error) {
	role := &models.RoleDefinition{
		Name:        req.Name,
		DisplayName: req.DisplayName,
		Description: req.Description,
	}
	if err := s.roleDefRepo.Create(ctx, role); err != nil {
		return nil, err
	}
	return role, nil
}

func (s *RoleAdminService) UpdateRole(ctx context.Context, id int64, req *dto.RoleDefinitionRequest) error {
	return s.roleDefRepo.Update(ctx, id, req.DisplayName, req.Description)
}

func (s *RoleAdminService) DeleteRole(ctx context.Context, id int64) error {
	return s.roleDefRepo.Delete(ctx, id)
}

func (s *RoleAdminService) GetUserRoles(ctx context.Context, userID int64) ([]models.UserRoleDetail, error) {
	return s.roleDefRepo.GetUserRoleDetails(ctx, userID)
}

func (s *RoleAdminService) AssignRoleToUser(ctx context.Context, userID int64, role string) error {
	// Add role with source='manual' so it is not overwritten by Auth sync
	if err := s.userRepo.AddRoleWithSource(ctx, userID, role, "manual"); err != nil {
		return err
	}

	if s.cache != nil {
		cache.Invalidate(ctx, s.cache, cache.KeyUserRoles(userID))
	}
	return nil
}

func (s *RoleAdminService) RemoveRoleFromUser(ctx context.Context, userID int64, role string) error {
	if err := s.roleDefRepo.RemoveRoleFromUser(ctx, userID, role); err != nil {
		return err
	}

	if s.cache != nil {
		cache.Invalidate(ctx, s.cache, cache.KeyUserRoles(userID))
	}
	return nil
}
