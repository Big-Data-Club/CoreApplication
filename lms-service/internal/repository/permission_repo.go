package repository

import (
	"context"
	"database/sql"
	"fmt"
	"strings"

	"example/hello/internal/models"
)

// PermissionRepository handles all permission-related database operations.
type PermissionRepository struct {
	db *sql.DB
}

func NewPermissionRepository(db *sql.DB) *PermissionRepository {
	return &PermissionRepository{db: db}
}

// FindAll returns every permission in the system (master list for UI).
func (r *PermissionRepository) FindAll(ctx context.Context) ([]models.Permission, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT id, code, module, COALESCE(description,''), created_at
		 FROM permissions ORDER BY module, code`)
	if err != nil {
		return nil, fmt.Errorf("FindAll permissions: %w", err)
	}
	defer rows.Close()

	var perms []models.Permission
	for rows.Next() {
		var p models.Permission
		if err := rows.Scan(&p.ID, &p.Code, &p.Module, &p.Description, &p.CreatedAt); err != nil {
			return nil, err
		}
		perms = append(perms, p)
	}
	return perms, rows.Err()
}

// FindByRoleID returns the role name and permissions currently assigned to a role ID.
// Uses a single JOIN query to avoid a separate GetRoleName roundtrip.
func (r *PermissionRepository) FindByRoleID(ctx context.Context, roleID int64) (roleName string, perms []models.Permission, err error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT rd.name, p.id, p.code, p.module, COALESCE(p.description,''), p.created_at
		 FROM role_definitions rd
		 LEFT JOIN role_permissions rp ON rp.role_id = rd.id
		 LEFT JOIN permissions p ON p.id = rp.permission_id
		 WHERE rd.id = $1
		 ORDER BY p.module, p.code`, roleID)
	if err != nil {
		return "", nil, fmt.Errorf("FindByRoleID: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var p models.Permission
		var pID sql.NullInt64
		var pCode, pModule, pDesc sql.NullString
		var pCreatedAt sql.NullTime
		if err := rows.Scan(&roleName, &pID, &pCode, &pModule, &pDesc, &pCreatedAt); err != nil {
			return "", nil, err
		}
		if pID.Valid {
			p.ID = pID.Int64
			p.Code = pCode.String
			p.Module = pModule.String
			p.Description = pDesc.String
			p.CreatedAt = pCreatedAt.Time
			perms = append(perms, p)
		}
	}
	if roleName == "" {
		return "", nil, fmt.Errorf("role not found: %d", roleID)
	}
	return roleName, perms, rows.Err()
}

// FindCodesByRoleName returns the permission code strings for a role name.
// Used by the middleware cache-miss path.
func (r *PermissionRepository) FindCodesByRoleName(ctx context.Context, roleName string) ([]string, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT p.code
		 FROM permissions p
		 JOIN role_permissions rp ON rp.permission_id = p.id
		 JOIN role_definitions rd ON rd.id = rp.role_id
		 WHERE rd.name = $1`, roleName)
	if err != nil {
		return nil, fmt.Errorf("FindCodesByRoleName: %w", err)
	}
	defer rows.Close()

	var codes []string
	for rows.Next() {
		var code string
		if err := rows.Scan(&code); err != nil {
			return nil, err
		}
		codes = append(codes, code)
	}
	return codes, rows.Err()
}

// AssignToRole replaces all permissions for a role in a single transaction.
func (r *PermissionRepository) AssignToRole(ctx context.Context, roleID int64, permissionIDs []int64) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer tx.Rollback()

	// Delete existing assignments
	if _, err := tx.ExecContext(ctx,
		`DELETE FROM role_permissions WHERE role_id = $1`, roleID); err != nil {
		return fmt.Errorf("delete old permissions: %w", err)
	}

	// Bulk insert new assignments
	if len(permissionIDs) > 0 {
		var sb strings.Builder
		sb.WriteString(`INSERT INTO role_permissions (role_id, permission_id) VALUES `)
		args := make([]interface{}, 0, len(permissionIDs)+1)
		args = append(args, roleID)

		for i, pid := range permissionIDs {
			if i > 0 {
				sb.WriteString(", ")
			}
			sb.WriteString(fmt.Sprintf("($1, $%d)", i+2))
			args = append(args, pid)
		}
		sb.WriteString(" ON CONFLICT DO NOTHING")

		if _, err := tx.ExecContext(ctx, sb.String(), args...); err != nil {
			return fmt.Errorf("insert permissions: %w", err)
		}
	}

	return tx.Commit()
}

// GetRoleName returns the name for a role ID.
// Kept for backwards compat but prefer FindByRoleID which fetches both in one query.
func (r *PermissionRepository) GetRoleName(ctx context.Context, roleID int64) (string, error) {
	var name string
	err := r.db.QueryRowContext(ctx,
		`SELECT name FROM role_definitions WHERE id = $1`, roleID).Scan(&name)
	if err != nil {
		return "", fmt.Errorf("GetRoleName: %w", err)
	}
	return name, nil
}
