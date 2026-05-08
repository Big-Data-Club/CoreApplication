package repository

import (
	"context"
	"database/sql"
	"fmt"
	"strings"

	"example/hello/internal/models"
)

type RoleDefinitionRepository struct {
	db *sql.DB
}

func NewRoleDefinitionRepository(db *sql.DB) *RoleDefinitionRepository {
	return &RoleDefinitionRepository{db: db}
}

func (r *RoleDefinitionRepository) FindAll(ctx context.Context) ([]models.RoleDefinition, error) {
	query := `SELECT id, name, display_name, description, is_system, created_at FROM role_definitions ORDER BY id`
	rows, err := r.db.QueryContext(ctx, query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var roles []models.RoleDefinition
	for rows.Next() {
		var role models.RoleDefinition
		var desc sql.NullString
		if err := rows.Scan(&role.ID, &role.Name, &role.DisplayName, &desc, &role.IsSystem, &role.CreatedAt); err != nil {
			return nil, err
		}
		if desc.Valid {
			role.Description = desc.String
		}
		roles = append(roles, role)
	}
	return roles, rows.Err()
}

func (r *RoleDefinitionRepository) Create(ctx context.Context, role *models.RoleDefinition) error {
	query := `
		INSERT INTO role_definitions (name, display_name, description, is_system)
		VALUES ($1, $2, $3, false)
		RETURNING id, created_at
	`
	name := strings.ToUpper(role.Name)
	return r.db.QueryRowContext(ctx, query, name, role.DisplayName, role.Description).
		Scan(&role.ID, &role.CreatedAt)
}

func (r *RoleDefinitionRepository) Update(ctx context.Context, id int64, displayName, description string) error {
	query := `UPDATE role_definitions SET display_name = $1, description = $2 WHERE id = $3`
	_, err := r.db.ExecContext(ctx, query, displayName, description, id)
	return err
}

func (r *RoleDefinitionRepository) Delete(ctx context.Context, id int64) error {
	// First check if it's a system role
	var isSystem bool
	err := r.db.QueryRowContext(ctx, `SELECT is_system FROM role_definitions WHERE id = $1`, id).Scan(&isSystem)
	if err != nil {
		if err == sql.ErrNoRows {
			return fmt.Errorf("role not found")
		}
		return err
	}
	if isSystem {
		return fmt.Errorf("cannot delete system role")
	}

	_, err = r.db.ExecContext(ctx, `DELETE FROM role_definitions WHERE id = $1`, id)
	return err
}

func (r *RoleDefinitionRepository) GetUserRoleDetails(ctx context.Context, userID int64) ([]models.UserRoleDetail, error) {
	query := `SELECT id, user_id, role, source, created_at FROM user_roles WHERE user_id = $1`
	rows, err := r.db.QueryContext(ctx, query, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var details []models.UserRoleDetail
	for rows.Next() {
		var detail models.UserRoleDetail
		var source sql.NullString
		if err := rows.Scan(&detail.ID, &detail.UserID, &detail.Role, &source, &detail.CreatedAt); err != nil {
			return nil, err
		}
		if source.Valid {
			detail.Source = source.String
		} else {
			detail.Source = "sync" // Default for older records
		}
		details = append(details, detail)
	}
	return details, rows.Err()
}

func (r *RoleDefinitionRepository) RemoveRoleFromUser(ctx context.Context, userID int64, role string) error {
	query := `DELETE FROM user_roles WHERE user_id = $1 AND role = $2`
	_, err := r.db.ExecContext(ctx, query, userID, role)
	return err
}
