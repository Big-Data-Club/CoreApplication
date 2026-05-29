package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"time"

	"example/hello/internal/dto"
	"example/hello/internal/models"
	"example/hello/internal/repository"
	"example/hello/pkg/cache"
	"example/hello/pkg/logger"
)

type OrganizationService struct {
	orgRepo    *repository.OrganizationRepository
	userRepo   *repository.UserRepository
	redisCache *cache.RedisCache
}

func NewOrganizationService(
	orgRepo *repository.OrganizationRepository,
	userRepo *repository.UserRepository,
	redisCache *cache.RedisCache,
) *OrganizationService {
	return &OrganizationService{
		orgRepo:    orgRepo,
		userRepo:   userRepo,
		redisCache: redisCache,
	}
}

var slugRegex = regexp.MustCompile("^[a-z0-9-_]+$")

// CachedUserOrgs represents the structure cached in Redis for user visibility filters
type CachedUserOrgs struct {
	OrgIDs        []int64 `json:"org_ids"`
	IncludePublic bool    `json:"include_public"`
}

func (s *OrganizationService) CreateOrganization(ctx context.Context, req *dto.CreateOrgRequest, creatorID int64, sysRole string) (*dto.OrgResponse, error) {
	if sysRole != models.RoleAdmin {
		return nil, errors.New("only Super Admin can create organizations")
	}

	if !slugRegex.MatchString(req.Slug) {
		return nil, errors.New("slug contains invalid characters (only alphanumeric, hyphens, and underscores allowed)")
	}

	// Check if slug already exists
	existing, err := s.orgRepo.GetBySlug(ctx, req.Slug)
	if err == nil && existing != nil {
		return nil, fmt.Errorf("organization with slug '%s' already exists", req.Slug)
	}

	// Build settings JSON for DB storage
	var settingsBytes []byte
	if req.Settings != nil {
		settingsBytes, _ = json.Marshal(models.OrgSettings{
			AllowCrossOrgCourses:    true,
			DefaultCourseVisibility: req.Settings.DefaultCourseVisibility,
			AllowSelfEnrollment:     req.Settings.AllowSelfEnrollment,
		})
	}
	if len(settingsBytes) == 0 {
		defaultSettings := models.OrgSettings{
			AllowCrossOrgCourses:    true,
			DefaultCourseVisibility: models.VisibilityPublic,
		}
		settingsBytes, _ = json.Marshal(defaultSettings)
	}

	org := &models.Organization{
		Name: req.Name,
		Slug: req.Slug,
		Description: sql.NullString{
			String: req.Description,
			Valid:  req.Description != "",
		},
		LogoURL: sql.NullString{
			String: req.LogoURL,
			Valid:  req.LogoURL != "",
		},
		Settings: settingsBytes,
		CreatedBy: sql.NullInt64{
			Int64: creatorID,
			Valid: true,
		},
	}

	newOrg, err := s.orgRepo.Create(ctx, org)
	if err != nil {
		return nil, err
	}

	// Auto add creator as OWNER of the new organization
	err = s.orgRepo.AddMember(ctx, newOrg.ID, creatorID, models.OrgRoleOwner)
	if err != nil {
		logger.Error("failed to add creator as organization owner", err)
	}

	// Invalidate user cached orgs
	s.invalidateUserOrgsCache(ctx, creatorID)

	return s.toOrgResponse(newOrg), nil
}

func (s *OrganizationService) GetOrganization(ctx context.Context, id int64) (*dto.OrgResponse, error) {
	org, err := s.orgRepo.GetByID(ctx, id)
	if err != nil {
		return nil, err
	}
	return s.toOrgResponse(org), nil
}

func (s *OrganizationService) GetOrganizationBySlug(ctx context.Context, slug string) (*dto.OrgResponse, error) {
	org, err := s.orgRepo.GetBySlug(ctx, slug)
	if err != nil {
		return nil, err
	}
	return s.toOrgResponse(org), nil
}

func (s *OrganizationService) ListOrganizations(ctx context.Context, limit, offset int, search string) ([]*dto.OrgResponse, int, error) {
	orgs, total, err := s.orgRepo.List(ctx, limit, offset, search)
	if err != nil {
		return nil, 0, err
	}

	resps := make([]*dto.OrgResponse, len(orgs))
	for i, org := range orgs {
		resps[i] = s.toOrgResponse(org)
	}

	return resps, total, nil
}

func (s *OrganizationService) UpdateOrganization(ctx context.Context, id int64, req *dto.UpdateOrgRequest, actorID int64, sysRole string) (*dto.OrgResponse, error) {
	// Check access: must be Super Admin or Org Admin/Owner
	hasAccess, err := s.checkOrgAccess(ctx, id, actorID, sysRole, models.OrgRoleAdmin)
	if err != nil {
		return nil, err
	}
	if !hasAccess {
		return nil, errors.New("unauthorized to update this organization")
	}

	org, err := s.orgRepo.GetByID(ctx, id)
	if err != nil {
		return nil, err
	}

	if req.Name != nil {
		org.Name = *req.Name
	}
	if req.Slug != nil {
		if !slugRegex.MatchString(*req.Slug) {
			return nil, errors.New("slug contains invalid characters")
		}
		// check unique slug
		if *req.Slug != org.Slug {
			existing, err := s.orgRepo.GetBySlug(ctx, *req.Slug)
			if err == nil && existing != nil {
				return nil, fmt.Errorf("organization with slug '%s' already exists", *req.Slug)
			}
			org.Slug = *req.Slug
		}
	}
	if req.Description != nil {
		org.Description = sql.NullString{String: *req.Description, Valid: *req.Description != ""}
	}
	if req.LogoURL != nil {
		org.LogoURL = sql.NullString{String: *req.LogoURL, Valid: *req.LogoURL != ""}
	}
	if req.Settings != nil {
		updatedSettings := models.OrgSettings{
			AllowCrossOrgCourses:    true,
			DefaultCourseVisibility: req.Settings.DefaultCourseVisibility,
			AllowSelfEnrollment:     req.Settings.AllowSelfEnrollment,
		}
		if b, err := json.Marshal(updatedSettings); err == nil {
			org.Settings = b
		}
	}

	updated, err := s.orgRepo.Update(ctx, org)
	if err != nil {
		return nil, err
	}

	// Invalidate caches
	s.invalidateAllOrgMembersCaches(ctx, id)

	return s.toOrgResponse(updated), nil
}

func (s *OrganizationService) DeactivateOrganization(ctx context.Context, id int64, sysRole string) error {
	if sysRole != models.RoleAdmin {
		return errors.New("only Super Admin can deactivate organizations")
	}

	// Check if this is the default bdc org, which cannot be deactivated
	org, err := s.orgRepo.GetByID(ctx, id)
	if err != nil {
		return err
	}
	if org.Slug == "bdc" {
		return errors.New("cannot deactivate the default Big Data Club organization")
	}

	err = s.orgRepo.SetActive(ctx, id, false)
	if err != nil {
		return err
	}

	s.invalidateAllOrgMembersCaches(ctx, id)
	return nil
}

func (s *OrganizationService) AddMember(ctx context.Context, orgID int64, req *dto.AddMemberRequest, actorID int64, sysRole string) error {
	hasAccess, err := s.checkOrgAccess(ctx, orgID, actorID, sysRole, models.OrgRoleAdmin)
	if err != nil {
		return err
	}
	if !hasAccess {
		return errors.New("unauthorized to manage members of this organization")
	}

	// Verify user exists
	_, err = s.userRepo.GetByID(ctx, req.UserID)
	if err != nil {
		if err == sql.ErrNoRows {
			return errors.New("user not found")
		}
		return err
	}

	err = s.orgRepo.AddMember(ctx, orgID, req.UserID, req.OrgRole)
	if err != nil {
		return err
	}

	s.invalidateUserOrgsCache(ctx, req.UserID)
	return nil
}

func (s *OrganizationService) RemoveMember(ctx context.Context, orgID int64, userID int64, actorID int64, sysRole string) error {
	// Actor must be Admin/Owner OR the user themselves leaving the org
	isSelf := actorID == userID
	var hasAccess bool
	var err error

	if isSelf {
		hasAccess = true
	} else {
		hasAccess, err = s.checkOrgAccess(ctx, orgID, actorID, sysRole, models.OrgRoleAdmin)
		if err != nil {
			return err
		}
	}

	if !hasAccess {
		return errors.New("unauthorized to remove this member")
	}

	// Check if this is the default bdc org, and user role inside is MEMBER.
	// We might want to allow it, but let's check.
	org, err := s.orgRepo.GetByID(ctx, orgID)
	if err != nil {
		return err
	}

	// If leaving owner, make sure there is at least one other owner
	_, currentRole, err := s.orgRepo.IsMember(ctx, orgID, userID)
	if err != nil {
		return err
	}

	if currentRole == models.OrgRoleOwner {
		members, _, err := s.orgRepo.ListMembers(ctx, orgID, 100, 0)
		if err == nil {
			ownerCount := 0
			for _, m := range members {
				if m.OrgRole == models.OrgRoleOwner {
					ownerCount++
				}
			}
			if ownerCount <= 1 && org.IsActive {
				return errors.New("cannot remove the last owner of an active organization")
			}
		}
	}

	err = s.orgRepo.RemoveMember(ctx, orgID, userID)
	if err != nil {
		return err
	}

	s.invalidateUserOrgsCache(ctx, userID)
	return nil
}

func (s *OrganizationService) UpdateMemberRole(ctx context.Context, orgID int64, userID int64, req *dto.UpdateMemberRoleRequest, actorID int64, sysRole string) error {
	hasAccess, err := s.checkOrgAccess(ctx, orgID, actorID, sysRole, models.OrgRoleAdmin)
	if err != nil {
		return err
	}
	if !hasAccess {
		return errors.New("unauthorized to update roles in this organization")
	}

	// Get member current role
	isMember, currentRole, err := s.orgRepo.IsMember(ctx, orgID, userID)
	if err != nil {
		return err
	}
	if !isMember {
		return errors.New("user is not a member of this organization")
	}

	// If changing from Owner, check last owner constraint
	if currentRole == models.OrgRoleOwner && req.OrgRole != models.OrgRoleOwner {
		members, _, err := s.orgRepo.ListMembers(ctx, orgID, 100, 0)
		if err == nil {
			ownerCount := 0
			for _, m := range members {
				if m.OrgRole == models.OrgRoleOwner {
					ownerCount++
				}
			}
			if ownerCount <= 1 {
				return errors.New("cannot change role of the last owner of this organization")
			}
		}
	}

	err = s.orgRepo.UpdateMemberRole(ctx, orgID, userID, req.OrgRole)
	if err != nil {
		return err
	}

	s.invalidateUserOrgsCache(ctx, userID)
	return nil
}

func (s *OrganizationService) ListMembers(ctx context.Context, orgID int64, limit, offset int) ([]*dto.OrgMemberResponse, int, error) {
	members, total, err := s.orgRepo.ListMembers(ctx, orgID, limit, offset)
	if err != nil {
		return nil, 0, err
	}

	resps := make([]*dto.OrgMemberResponse, len(members))
	for i, m := range members {
		resps[i] = &dto.OrgMemberResponse{
			UserID:   m.UserID,
			FullName: m.FullName,
			Email:    m.Email,
			OrgRole:  m.OrgRole,
			JoinedAt: m.JoinedAt,
		}
	}

	return resps, total, nil
}

func (s *OrganizationService) GetUserOrgs(ctx context.Context, userID int64) ([]*dto.OrgResponse, error) {
	orgs, err := s.orgRepo.GetUserOrgs(ctx, userID)
	if err != nil {
		return nil, err
	}

	resps := make([]*dto.OrgResponse, len(orgs))
	for i, org := range orgs {
		resps[i] = s.toOrgResponse(org)
	}

	return resps, nil
}

// GetVisibleCourseFilter builds the CourseVisibilityFilter for queries, utilizing Redis caching
func (s *OrganizationService) GetVisibleCourseFilter(ctx context.Context, userID int64) (repository.CourseVisibilityFilter, error) {
	cacheKey := fmt.Sprintf("user_orgs:%d", userID)
	
	// Try cache
	if cachedVal, err := s.redisCache.Get(ctx, cacheKey); err == nil {
		var cached CachedUserOrgs
		if err := json.Unmarshal([]byte(cachedVal), &cached); err == nil {
			return repository.CourseVisibilityFilter{
				UserOrgIDs:    cached.OrgIDs,
				IncludePublic: cached.IncludePublic,
			}, nil
		}
	}

	// Cache miss: load from DB
	orgs, err := s.orgRepo.GetUserOrgs(ctx, userID)
	if err != nil {
		return repository.CourseVisibilityFilter{}, err
	}

	orgIDs := make([]int64, len(orgs))
	includePublic := false

	for i, org := range orgs {
		orgIDs[i] = org.ID
		var settings models.OrgSettings
		if err := json.Unmarshal(org.Settings, &settings); err == nil {
			if settings.AllowCrossOrgCourses {
				includePublic = true
			}
		}
	}

	// Always ensure default bdc org is handled if empty
	if len(orgIDs) == 0 {
		// Fallback: lookup bdc org
		bdcOrg, err := s.orgRepo.GetBySlug(ctx, "bdc")
		if err == nil && bdcOrg != nil {
			// If not enrolled, let's include it or default to include public courses.
			// By default, since they have no orgs, they might see BDC's public courses.
			includePublic = true
		}
	}

	// Save to cache (5 min TTL)
	cached := CachedUserOrgs{
		OrgIDs:        orgIDs,
		IncludePublic: includePublic,
	}
	if bytes, err := json.Marshal(cached); err == nil {
		s.redisCache.Set(ctx, cacheKey, bytes, 5*time.Minute)
	}

	return repository.CourseVisibilityFilter{
		UserOrgIDs:    orgIDs,
		IncludePublic: includePublic,
	}, nil
}

// GetOrgStats returns stats with Redis caching (60s TTL)
func (s *OrganizationService) GetOrgStats(ctx context.Context, orgID int64) (*dto.OrgStatsResponse, error) {
	cacheKey := fmt.Sprintf("org_stats:%d", orgID)

	if cachedVal, err := s.redisCache.Get(ctx, cacheKey); err == nil {
		var cached dto.OrgStatsResponse
		if err := json.Unmarshal([]byte(cachedVal), &cached); err == nil {
			return &cached, nil
		}
	}

	stats, err := s.orgRepo.GetStats(ctx, orgID)
	if err != nil {
		return nil, err
	}

	resp := &dto.OrgStatsResponse{
		OrgID:         stats.OrgID,
		MemberCount:   stats.MemberCount,
		CourseCount:   stats.CourseCount,
		EnrolledCount: stats.EnrolledCount,
	}

	if bytes, err := json.Marshal(resp); err == nil {
		s.redisCache.Set(ctx, cacheKey, bytes, 60*time.Second)
	}

	return resp, nil
}

// Check if actor belongs to the org with at least the requiredRole (Owner > Admin > Member)
func (s *OrganizationService) checkOrgAccess(ctx context.Context, orgID int64, actorID int64, sysRole string, requiredRole string) (bool, error) {
	// Super Admin always has full access
	if sysRole == models.RoleAdmin {
		return true, nil
	}

	isMember, role, err := s.orgRepo.IsMember(ctx, orgID, actorID)
	if err != nil {
		return false, err
	}
	if !isMember {
		return false, nil
	}

	// Role ranking evaluation
	switch requiredRole {
	case models.OrgRoleOwner:
		return role == models.OrgRoleOwner, nil
	case models.OrgRoleAdmin:
		return role == models.OrgRoleOwner || role == models.OrgRoleAdmin, nil
	default:
		return true, nil // MEMBER role or any
	}
}

func (s *OrganizationService) invalidateUserOrgsCache(ctx context.Context, userID int64) {
	cacheKey := fmt.Sprintf("user_orgs:%d", userID)
	_ = s.redisCache.Delete(ctx, cacheKey)
}

func (s *OrganizationService) invalidateAllOrgMembersCaches(ctx context.Context, orgID int64) {
	// Invalidate org stats
	statsKey := fmt.Sprintf("org_stats:%d", orgID)
	_ = s.redisCache.Delete(ctx, statsKey)

	// Invalidate all members' visibility caches
	limit := 100
	offset := 0
	for {
		members, _, err := s.orgRepo.ListMembers(ctx, orgID, limit, offset)
		if err != nil || len(members) == 0 {
			break
		}
		for _, m := range members {
			s.invalidateUserOrgsCache(ctx, m.UserID)
		}
		offset += limit
	}
}

func (s *OrganizationService) toOrgResponse(org *models.Organization) *dto.OrgResponse {
	var desc, logo string
	if org.Description.Valid {
		desc = org.Description.String
	}
	if org.LogoURL.Valid {
		logo = org.LogoURL.String
	}

	var createdBy *int64
	if org.CreatedBy.Valid {
		createdBy = &org.CreatedBy.Int64
	}

	// Unmarshal stored JSON settings into the typed DTO
	var settingsDTO *dto.OrgSettingsDTO
	if len(org.Settings) > 0 {
		var ms models.OrgSettings
		if err := json.Unmarshal(org.Settings, &ms); err == nil {
			settingsDTO = &dto.OrgSettingsDTO{
				AllowSelfEnrollment:     ms.AllowSelfEnrollment,
				DefaultCourseVisibility: ms.DefaultCourseVisibility,
			}
			if ms.MaxMembers > 0 {
				m := ms.MaxMembers
				settingsDTO.MaxMembers = &m
			}
		}
	}

	return &dto.OrgResponse{
		ID:          org.ID,
		Name:        org.Name,
		Slug:        org.Slug,
		Description: desc,
		LogoURL:     logo,
		IsActive:    org.IsActive,
		Settings:    settingsDTO,
		CreatedBy:   createdBy,
		CreatedAt:   org.CreatedAt,
		UpdatedAt:   org.UpdatedAt,
	}
}
