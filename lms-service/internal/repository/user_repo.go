package repository

import (
	"context"
	"database/sql"
	"fmt"

	"example/hello/internal/models"
	"github.com/lib/pq"
)

type UserRepository struct {
	db *sql.DB
}

func NewUserRepository(db *sql.DB) *UserRepository {
	return &UserRepository{db: db}
}

func (r *UserRepository) GetDB() *sql.DB {
	return r.db
}

// GetOrCreateUser gets user by ID or creates if not exists
func (r *UserRepository) GetOrCreateUser(ctx context.Context, userID int64, email, fullName, organization string) (*models.User, error) {
	// Try to get user first
	user, err := r.GetByID(ctx, userID)
	if err == nil {
		return user, nil
	}

	// If not found, create user
	if err == sql.ErrNoRows {
		return r.Create(ctx, userID, email, fullName, organization)
	}

	return nil, err
}

// GetByID retrieves a user by ID
func (r *UserRepository) GetByID(ctx context.Context, id int64) (*models.User, error) {
	query := `SELECT id, email, full_name, COALESCE(organization, ''), created_at, updated_at FROM users WHERE id = $1`

	var user models.User
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&user.ID,
		&user.Email,
		&user.FullName,
		&user.Organization,
		&user.CreatedAt,
		&user.UpdatedAt,
	)

	if err != nil {
		return nil, err
	}

	return &user, nil
}

// Create creates a new user
func (r *UserRepository) Create(ctx context.Context, id int64, email, fullName, organization string) (*models.User, error) {
	query := `
		INSERT INTO users (id, email, full_name, organization)
		VALUES ($1, $2, $3, $4)
		RETURNING id, email, full_name, COALESCE(organization, ''), created_at, updated_at
	`

	var user models.User
	err := r.db.QueryRowContext(ctx, query, id, email, fullName, organization).Scan(
		&user.ID,
		&user.Email,
		&user.FullName,
		&user.Organization,
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

// ClearSyncedRoles removes only roles with source='sync', preserving manual overrides.
func (r *UserRepository) ClearSyncedRoles(ctx context.Context, userID int64) error {
	query := `DELETE FROM user_roles WHERE user_id = $1 AND source = 'sync'`
	_, err := r.db.ExecContext(ctx, query, userID)
	return err
}

// AddRoleWithSource inserts a role with an explicit source tag ('sync' or 'manual').
func (r *UserRepository) AddRoleWithSource(ctx context.Context, userID int64, role, source string) error {
	query := `
		INSERT INTO user_roles (user_id, role, source)
		VALUES ($1, $2, $3)
		ON CONFLICT (user_id, role) DO NOTHING
	`
	_, err := r.db.ExecContext(ctx, query, userID, role, source)
	return err
}

// GetByEmails retrieves multiple users by their emails in a single query
func (r *UserRepository) GetByEmails(ctx context.Context, emails []string) ([]*models.User, error) {
	if len(emails) == 0 {
		return nil, nil
	}

	query := `SELECT id, email, full_name, COALESCE(organization, ''), created_at, updated_at FROM users WHERE email = ANY($1)`

	rows, err := r.db.QueryContext(ctx, query, pq.Array(emails))
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var users []*models.User
	for rows.Next() {
		var user models.User
		err := rows.Scan(
			&user.ID,
			&user.Email,
			&user.FullName,
			&user.Organization,
			&user.CreatedAt,
			&user.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}
		users = append(users, &user)
	}

	if err = rows.Err(); err != nil {
		return nil, err
	}

	return users, nil
}

// UpdateOrganization updates user's organization
func (r *UserRepository) UpdateOrganization(ctx context.Context, userID int64, organization string) error {
	query := `UPDATE users SET organization = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2`

	result, err := r.db.ExecContext(ctx, query, organization, userID)
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

// AssociateUserWithOrganization checks if organization exists by name or slug, and adds user as MEMBER
func (r *UserRepository) AssociateUserWithOrganization(ctx context.Context, userID int64, orgNameOrSlug string) error {
	if orgNameOrSlug == "" {
		return nil
	}
	// 1. Find organization id by name or slug
	var orgID int64
	queryFind := `SELECT id FROM organizations WHERE name = $1 OR slug = $2`
	err := r.db.QueryRowContext(ctx, queryFind, orgNameOrSlug, orgNameOrSlug).Scan(&orgID)
	if err == sql.ErrNoRows {
		// If org doesn't exist, we don't do anything (silent ignore)
		return nil
	} else if err != nil {
		return err
	}

	// 2. Insert into organization_members
	queryInsert := `
		INSERT INTO organization_members (org_id, user_id, org_role)
		VALUES ($1, $2, 'MEMBER')
		ON CONFLICT (org_id, user_id) DO NOTHING
	`
	_, err = r.db.ExecContext(ctx, queryInsert, orgID, userID)
	return err
}

// SearchTeachers searches for users with TEACHER role by name or email
func (r *UserRepository) SearchTeachers(ctx context.Context, queryStr string) ([]*models.User, error) {
	query := `
		SELECT u.id, u.email, u.full_name, COALESCE(u.organization, ''), u.created_at, u.updated_at
		FROM users u
		JOIN user_roles ur ON u.id = ur.user_id
		WHERE ur.role = 'TEACHER'
		  AND (u.email ILIKE $1 OR u.full_name ILIKE $1)
		ORDER BY u.full_name ASC
		LIMIT 10
	`
	rows, err := r.db.QueryContext(ctx, query, "%"+queryStr+"%")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var users []*models.User
	for rows.Next() {
		var user models.User
		err := rows.Scan(
			&user.ID,
			&user.Email,
			&user.FullName,
			&user.Organization,
			&user.CreatedAt,
			&user.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}
		users = append(users, &user)
	}

	return users, rows.Err()
}