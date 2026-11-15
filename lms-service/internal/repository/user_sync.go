package repository

import (
	"context"
	"database/sql"

	"example/hello/internal/dto"
)

func (r *UserRepository) SyncOrganization(ctx context.Context, req *dto.OrgSyncRequest) error {
	query := `
		INSERT INTO organizations (id, name, slug, description, logo_url, is_active, settings)
		VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
		ON CONFLICT (id) DO UPDATE SET
			name = EXCLUDED.name,
			slug = EXCLUDED.slug,
			description = EXCLUDED.description,
			logo_url = EXCLUDED.logo_url,
			is_active = EXCLUDED.is_active,
			settings = EXCLUDED.settings,
			updated_at = CURRENT_TIMESTAMP
	`
	var desc, logo sql.NullString
	if req.Description != "" {
		desc = sql.NullString{String: req.Description, Valid: true}
	}
	if req.LogoURL != "" {
		logo = sql.NullString{String: req.LogoURL, Valid: true}
	}

	_, err := r.db.ExecContext(ctx, query,
		req.ID,
		req.Name,
		req.Slug,
		desc,
		logo,
		req.IsActive,
		req.Settings,
	)
	return err
}
func (r *UserRepository) DeleteOrganization(ctx context.Context, orgID int64) error {
	query := `DELETE FROM organizations WHERE id = $1`
	_, err := r.db.ExecContext(ctx, query, orgID)
	return err
}
func (r *UserRepository) SyncOrganizationMember(ctx context.Context, req *dto.OrgMemberSyncRequest) error {
	query := `
		INSERT INTO organization_members (org_id, user_id, org_role)
		VALUES ($1, $2, $3)
		ON CONFLICT (org_id, user_id) DO UPDATE SET
			org_role = EXCLUDED.org_role
	`
	_, err := r.db.ExecContext(ctx, query, req.OrgID, req.UserID, req.OrgRole)
	return err
}
func (r *UserRepository) RemoveOrganizationMember(ctx context.Context, orgID, userID int64) error {
	query := `DELETE FROM organization_members WHERE org_id = $1 AND user_id = $2`
	_, err := r.db.ExecContext(ctx, query, orgID, userID)
	return err
}
