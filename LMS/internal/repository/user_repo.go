package repository

import (
	"context"
	"database/sql"
	"fmt"

	"example/hello/internal/models"
)

type UserRepository struct {
	db *sql.DB
}

func NewUserRepository(db *sql.DB) *UserRepository {
	return &UserRepository{db: db}
}

// GetOrCreateUser gets user by ID or creates if not exists
func (r *UserRepository) GetOrCreateUser(ctx context.Context, userID int64, email, fullName string) (*models.User, error) {
	// Try to get user first
	user, err := r.GetByID(ctx, userID)
	if err == nil {
		return user, nil
	}

	// If not found, create user
	if err == sql.ErrNoRows {
		return r.Create(ctx, userID, email, fullName)
	}

	return nil, err
}

// GetByID retrieves a user by ID
func (r *UserRepository) GetByID(ctx context.Context, id int64) (*models.User, error) {
	query := `SELECT id, email, full_name, created_at, updated_at FROM users WHERE id = $1`

	var user models.User
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&user.ID,
		&user.Email,
		&user.FullName,
		&user.CreatedAt,
		&user.UpdatedAt,
	)

	if err != nil {
		return nil, err
	}

	return &user, nil
}

// Create creates a new user
func (r *UserRepository) Create(ctx context.Context, id int64, email, fullName string) (*models.User, error) {
	query := `
		INSERT INTO users (id, email, full_name)
		VALUES ($1, $2, $3)
		RETURNING id, email, full_name, created_at, updated_at
	`

	var user models.User
	err := r.db.QueryRowContext(ctx, query, id, email, fullName).Scan(
		&user.ID,
		&user.Email,
		&user.FullName,
		&user.CreatedAt,
		&user.UpdatedAt,
	)

	if err != nil {
		return nil, err
	}

	return &user, nil
}

// UpdateFullName updates user's full name
func (r *UserRepository) UpdateFullName(ctx context.Context, userID int64, fullName string) error {
	query := `UPDATE users SET full_name = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2`

	result, err := r.db.ExecContext(ctx, query, fullName, userID)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}

	if rows == 0 {
		return fmt.Errorf("user not found")
	}

	return nil
}

// GetUserRoles retrieves all roles for a user
func (r *UserRepository) GetUserRoles(ctx context.Context, userID int64) ([]string, error) {
	query := `SELECT role FROM user_roles WHERE user_id = $1 ORDER BY role`

	rows, err := r.db.QueryContext(ctx, query, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var roles []string
	for rows.Next() {
		var role string
		if err := rows.Scan(&role); err != nil {
			return nil, err
		}
		roles = append(roles, role)
	}

	if err = rows.Err(); err != nil {
		return nil, err
	}

	// If no roles found, return empty array (not default to STUDENT)
	// This is important for sync operations
	return roles, nil
}

// AddRole adds a role to a user
func (r *UserRepository) AddRole(ctx context.Context, userID int64, role string) error {
	query := `
		INSERT INTO user_roles (user_id, role)
		VALUES ($1, $2)
		ON CONFLICT (user_id, role) DO NOTHING
	`

	_, err := r.db.ExecContext(ctx, query, userID, role)
	return err
}

// RemoveRole removes a role from a user
func (r *UserRepository) RemoveRole(ctx context.Context, userID int64, role string) error {
	query := `DELETE FROM user_roles WHERE user_id = $1 AND role = $2`

	result, err := r.db.ExecContext(ctx, query, userID, role)
	if err != nil {
		return err
	}

	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}

	if rows == 0 {
		return fmt.Errorf("role not found")
	}

	return nil
}

// HasRole checks if user has a specific role
func (r *UserRepository) HasRole(ctx context.Context, userID int64, role string) (bool, error) {
	query := `SELECT EXISTS(SELECT 1 FROM user_roles WHERE user_id = $1 AND role = $2)`

	var exists bool
	err := r.db.QueryRowContext(ctx, query, userID, role).Scan(&exists)
	if err != nil {
		return false, err
	}

	return exists, nil
}

// ClearUserRoles removes all roles from a user
func (r *UserRepository) ClearUserRoles(ctx context.Context, userID int64) error {
	query := `DELETE FROM user_roles WHERE user_id = $1`
	_, err := r.db.ExecContext(ctx, query, userID)
	return err
}