package service

import (
	"context"

	"example/hello/internal/dto"
	"example/hello/internal/repository"
)

type UserService struct {
	userRepo *repository.UserRepository
}

func NewUserService(userRepo *repository.UserRepository) *UserService {
	return &UserService{
		userRepo: userRepo,
	}
}

// GetMyRoles retrieves the roles for the authenticated user
func (s *UserService) GetMyRoles(ctx context.Context, userID int64, email string) (*dto.UserRolesResponse, error) {
	// Ensure user exists in database
	_, err := s.userRepo.GetOrCreateUser(ctx, userID, email, "")
	if err != nil {
		return nil, err
	}

	// Get user roles
	roles, err := s.userRepo.GetUserRoles(ctx, userID)
	if err != nil {
		return nil, err
	}

	return &dto.UserRolesResponse{
		UserID: userID,
		Email:  email,
		Roles:  roles,
	}, nil
}