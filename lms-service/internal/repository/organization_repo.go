package repository

import (
	"context"
	"database/sql"

	"example/hello/internal/models"
)

type OrganizationRepository struct {
	db *sql.DB
}

func NewOrganizationRepository(db *sql.DB) *OrganizationRepository {
	return &OrganizationRepository{db: db}
}

// Create creates a new organization
func (r *OrganizationRepository) Create(ctx context.Context, org *models.Organization) (*models.Organization, error) {
	query := `
		INSERT INTO organizations (name, slug, description, logo_url, settings, created_by)
		VALUES ($1, $2, $3, $4, $5, $6)
		RETURNING id, name, slug, description, logo_url, is_active, settings, created_by, created_at, updated_at
	`

	var description, logoURL sql.NullString
	if org.Description.Valid {
		description = org.Description
	}
	if org.LogoURL.Valid {
		logoURL = org.LogoURL
	}

	var createdBy sql.NullInt64
	if org.CreatedBy.Valid {
		createdBy = org.CreatedBy
	}

	var newOrg models.Organization
	err := r.db.QueryRowContext(ctx, query,
		org.Name,
		org.Slug,
		description,
		logoURL,
		org.Settings,
		createdBy,
	).Scan(
		&newOrg.ID,
		&newOrg.Name,
		&newOrg.Slug,
		&newOrg.Description,
		&newOrg.LogoURL,
		&newOrg.IsActive,
		&newOrg.Settings,
		&newOrg.CreatedBy,
		&newOrg.CreatedAt,
		&newOrg.UpdatedAt,
	)

	if err != nil {
		return nil, err
	}

	return &newOrg, nil
}

// GetByID retrieves an organization by ID
func (r *OrganizationRepository) GetByID(ctx context.Context, id int64) (*models.Organization, error) {
	query := `
		SELECT id, name, slug, description, logo_url, is_active, settings, created_by, created_at, updated_at
		FROM organizations
		WHERE id = $1
	`

	var org models.Organization
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&org.ID,
		&org.Name,
		&org.Slug,
		&org.Description,
		&org.LogoURL,
		&org.IsActive,
		&org.Settings,
		&org.CreatedBy,
		&org.CreatedAt,
		&org.UpdatedAt,
	)

	if err != nil {
		return nil, err
	}

	return &org, nil
}

// GetBySlug retrieves an organization by Slug
func (r *OrganizationRepository) GetBySlug(ctx context.Context, slug string) (*models.Organization, error) {
	query := `
		SELECT id, name, slug, description, logo_url, is_active, settings, created_by, created_at, updated_at
		FROM organizations
		WHERE slug = $1
	`

	var org models.Organization
	err := r.db.QueryRowContext(ctx, query, slug).Scan(
		&org.ID,
		&org.Name,
		&org.Slug,
		&org.Description,
		&org.LogoURL,
		&org.IsActive,
		&org.Settings,
		&org.CreatedBy,
		&org.CreatedAt,
		&org.UpdatedAt,
	)

	if err != nil {
		return nil, err
	}

	return &org, nil
}

// List lists organizations with pagination and search
func (r *OrganizationRepository) List(ctx context.Context, limit, offset int, search string) ([]*models.Organization, int, error) {
	var countQuery string
	var query string
	var args []interface{}
	var countArgs []interface{}

	if search != "" {
		countQuery = `SELECT COUNT(*) FROM organizations WHERE name ILIKE $1 OR slug ILIKE $1`
		query = `
			SELECT id, name, slug, description, logo_url, is_active, settings, created_by, created_at, updated_at
			FROM organizations
			WHERE name ILIKE $1 OR slug ILIKE $1
			ORDER BY name ASC
			LIMIT $2 OFFSET $3
		`
		searchParam := "%" + search + "%"
		countArgs = append(countArgs, searchParam)
		args = append(args, searchParam, limit, offset)
	} else {
		countQuery = `SELECT COUNT(*) FROM organizations`
		query = `
			SELECT id, name, slug, description, logo_url, is_active, settings, created_by, created_at, updated_at
			FROM organizations
			ORDER BY name ASC
			LIMIT $1 OFFSET $2
		`
		args = append(args, limit, offset)
	}

	var total int
	err := r.db.QueryRowContext(ctx, countQuery, countArgs...).Scan(&total)
	if err != nil {
		return nil, 0, err
	}

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	var orgs []*models.Organization
	for rows.Next() {
		var org models.Organization
		err := rows.Scan(
			&org.ID,
			&org.Name,
			&org.Slug,
			&org.Description,
			&org.LogoURL,
			&org.IsActive,
			&org.Settings,
			&org.CreatedBy,
			&org.CreatedAt,
			&org.UpdatedAt,
		)
		if err != nil {
			return nil, 0, err
		}
		orgs = append(orgs, &org)
	}

	if err = rows.Err(); err != nil {
		return nil, 0, err
	}

	return orgs, total, nil
}

// Update updates an organization's fields
func (r *OrganizationRepository) Update(ctx context.Context, org *models.Organization) (*models.Organization, error) {
	query := `
		UPDATE organizations
		SET name = $1, slug = $2, description = $3, logo_url = $4, settings = $5, updated_at = CURRENT_TIMESTAMP
		WHERE id = $6
		RETURNING id, name, slug, description, logo_url, is_active, settings, created_by, created_at, updated_at
	`

	var updatedOrg models.Organization
	err := r.db.QueryRowContext(ctx, query,
		org.Name,
		org.Slug,
		org.Description,
		org.LogoURL,
		org.Settings,
		org.ID,
	).Scan(
		&updatedOrg.ID,
		&updatedOrg.Name,
		&updatedOrg.Slug,
		&updatedOrg.Description,
		&updatedOrg.LogoURL,
		&updatedOrg.IsActive,
		&updatedOrg.Settings,
		&updatedOrg.CreatedBy,
		&updatedOrg.CreatedAt,
		&updatedOrg.UpdatedAt,
	)

	if err != nil {
		return nil, err
	}

	return &updatedOrg, nil
}

// SetActive toggles active status of an organization
func (r *OrganizationRepository) SetActive(ctx context.Context, id int64, isActive bool) error {
	query := `UPDATE organizations SET is_active = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2`
	result, err := r.db.ExecContext(ctx, query, isActive, id)
	if err != nil {
		return err
	}
	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if rows == 0 {
		return sql.ErrNoRows
	}
	return nil
}

// AddMember adds a user to an organization
func (r *OrganizationRepository) AddMember(ctx context.Context, orgID, userID int64, role string) error {
	query := `
		INSERT INTO organization_members (org_id, user_id, org_role)
		VALUES ($1, $2, $3)
		ON CONFLICT (org_id, user_id) DO UPDATE SET org_role = EXCLUDED.org_role
	`
	_, err := r.db.ExecContext(ctx, query, orgID, userID, role)
	return err
}

// RemoveMember removes a user from an organization
func (r *OrganizationRepository) RemoveMember(ctx context.Context, orgID, userID int64) error {
	query := `DELETE FROM organization_members WHERE org_id = $1 AND user_id = $2`
	result, err := r.db.ExecContext(ctx, query, orgID, userID)
	if err != nil {
		return err
	}
	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if rows == 0 {
		return sql.ErrNoRows
	}
	return nil
}

// UpdateMemberRole updates a member's role
func (r *OrganizationRepository) UpdateMemberRole(ctx context.Context, orgID, userID int64, role string) error {
	query := `UPDATE organization_members SET org_role = $1 WHERE org_id = $2 AND user_id = $3`
	result, err := r.db.ExecContext(ctx, query, role, orgID, userID)
	if err != nil {
		return err
	}
	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if rows == 0 {
		return sql.ErrNoRows
	}
	return nil
}

// ListMembers lists members of an organization with pagination
func (r *OrganizationRepository) ListMembers(ctx context.Context, orgID int64, limit, offset int) ([]*models.OrgMemberWithUserInfo, int, error) {
	countQuery := `SELECT COUNT(*) FROM organization_members WHERE org_id = $1`
	var total int
	err := r.db.QueryRowContext(ctx, countQuery, orgID).Scan(&total)
	if err != nil {
		return nil, 0, err
	}

	query := `
		SELECT om.user_id, u.full_name, u.email, om.org_role, om.joined_at
		FROM organization_members om
		JOIN users u ON om.user_id = u.id
		WHERE om.org_id = $1
		ORDER BY u.full_name ASC
		LIMIT $2 OFFSET $3
	`

	rows, err := r.db.QueryContext(ctx, query, orgID, limit, offset)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	var members []*models.OrgMemberWithUserInfo
	for rows.Next() {
		var m models.OrgMemberWithUserInfo
		err := rows.Scan(
			&m.UserID,
			&m.FullName,
			&m.Email,
			&m.OrgRole,
			&m.JoinedAt,
		)
		if err != nil {
			return nil, 0, err
		}
		members = append(members, &m)
	}

	if err = rows.Err(); err != nil {
		return nil, 0, err
	}

	return members, total, nil
}

// GetUserOrgs retrieves all organizations a user belongs to
func (r *OrganizationRepository) GetUserOrgs(ctx context.Context, userID int64) ([]*models.Organization, error) {
	query := `
		SELECT o.id, o.name, o.slug, o.description, o.logo_url, o.is_active, o.settings, o.created_by, o.created_at, o.updated_at
		FROM organizations o
		JOIN organization_members om ON o.id = om.org_id
		WHERE om.user_id = $1 AND o.is_active = true
		ORDER BY o.name ASC
	`

	rows, err := r.db.QueryContext(ctx, query, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var orgs []*models.Organization
	for rows.Next() {
		var org models.Organization
		err := rows.Scan(
			&org.ID,
			&org.Name,
			&org.Slug,
			&org.Description,
			&org.LogoURL,
			&org.IsActive,
			&org.Settings,
			&org.CreatedBy,
			&org.CreatedAt,
			&org.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}
		orgs = append(orgs, &org)
	}

	if err = rows.Err(); err != nil {
		return nil, err
	}

	return orgs, nil
}

// GetUserOrgIDs retrieves only organization IDs a user belongs to (hot path)
func (r *OrganizationRepository) GetUserOrgIDs(ctx context.Context, userID int64) ([]int64, error) {
	query := `
		SELECT om.org_id
		FROM organization_members om
		JOIN organizations o ON om.org_id = o.id
		WHERE om.user_id = $1 AND o.is_active = true
	`

	rows, err := r.db.QueryContext(ctx, query, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var ids []int64
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}

	if err = rows.Err(); err != nil {
		return nil, err
	}

	return ids, nil
}

// IsMember checks if a user is a member of an organization, and returns their role
func (r *OrganizationRepository) IsMember(ctx context.Context, orgID, userID int64) (bool, string, error) {
	query := `SELECT org_role FROM organization_members WHERE org_id = $1 AND user_id = $2`

	var role string
	err := r.db.QueryRowContext(ctx, query, orgID, userID).Scan(&role)
	if err == sql.ErrNoRows {
		return false, "", nil
	} else if err != nil {
		return false, "", err
	}

	return true, role, nil
}

// GetStats returns organization statistics
func (r *OrganizationRepository) GetStats(ctx context.Context, orgID int64) (*models.OrgStats, error) {
	stats := &models.OrgStats{OrgID: orgID}

	// 1. Member Count
	err := r.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM organization_members WHERE org_id = $1`, orgID).Scan(&stats.MemberCount)
	if err != nil {
		return nil, err
	}

	// 2. Course Count
	err = r.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM courses WHERE org_id = $1`, orgID).Scan(&stats.CourseCount)
	if err != nil {
		return nil, err
	}

	// 3. Enrolled Count (Sum of enrollments for courses belonging to this organization)
	err = r.db.QueryRowContext(ctx, `
		SELECT COUNT(e.id)
		FROM enrollments e
		JOIN courses c ON e.course_id = c.id
		WHERE c.org_id = $1
	`, orgID).Scan(&stats.EnrolledCount)
	if err != nil {
		return nil, err
	}

	return stats, nil
}
