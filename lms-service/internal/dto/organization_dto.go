package dto

import "time"

// OrgSettingsDTO represents the settings of an organization.
// Replaces json.RawMessage so that swag can generate Swagger docs.
type OrgSettingsDTO struct {
	AllowSelfEnrollment        bool   `json:"allow_self_enrollment"`
	DefaultCourseVisibility    string `json:"default_course_visibility" enums:"PUBLIC,ORG_ONLY"`
	MaxMembers                 *int   `json:"max_members,omitempty"`
}

// CreateOrgRequest represents the request to create an organization
type CreateOrgRequest struct {
	Name        string          `json:"name"        binding:"required,min=2,max=255"`
	Slug        string          `json:"slug"        binding:"required,min=2,max=100"`
	Description string          `json:"description" binding:"max=2000"`
	LogoURL     string          `json:"logo_url"    binding:"omitempty,max=500"`
	Settings    *OrgSettingsDTO `json:"settings"    binding:"omitempty"`
}

// UpdateOrgRequest represents the request to update an organization
type UpdateOrgRequest struct {
	Name        *string         `json:"name"        binding:"omitempty,min=2,max=255"`
	Slug        *string         `json:"slug"        binding:"omitempty,min=2,max=100"`
	Description *string         `json:"description" binding:"omitempty,max=2000"`
	LogoURL     *string         `json:"logo_url"    binding:"omitempty,max=500"`
	Settings    *OrgSettingsDTO `json:"settings"    binding:"omitempty"`
}

// OrgResponse represents the response for an organization
type OrgResponse struct {
	ID          int64           `json:"id"`
	Name        string          `json:"name"`
	Slug        string          `json:"slug"`
	Description string          `json:"description,omitempty"`
	LogoURL     string          `json:"logo_url,omitempty"`
	IsActive    bool            `json:"is_active"`
	Settings    *OrgSettingsDTO `json:"settings,omitempty"`
	CreatedBy   *int64          `json:"created_by,omitempty"`
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
}

// AddMemberRequest represents the request to add a member to an organization
type AddMemberRequest struct {
	UserID  int64  `json:"user_id"  binding:"required"`
	OrgRole string `json:"org_role" binding:"required,oneof=OWNER ADMIN MEMBER"`
}

// UpdateMemberRoleRequest represents the request to update a member's role
type UpdateMemberRoleRequest struct {
	OrgRole string `json:"org_role" binding:"required,oneof=OWNER ADMIN MEMBER"`
}

// OrgMemberResponse represents the response for an organization member
type OrgMemberResponse struct {
	UserID   int64     `json:"user_id"`
	FullName string    `json:"full_name"`
	Email    string    `json:"email"`
	OrgRole  string    `json:"org_role"`
	JoinedAt time.Time `json:"joined_at"`
}

// OrgStatsResponse represents the response for organization statistics
type OrgStatsResponse struct {
	OrgID         int64 `json:"org_id"`
	MemberCount   int   `json:"member_count"`
	CourseCount   int   `json:"course_count"`
	EnrolledCount int   `json:"enrolled_count"`
}

// BulkAddMembersRequest represents the request to bulk add members by email or raw text input
type BulkAddMembersRequest struct {
	Emails   []string `json:"emails"`
	RawInput string   `json:"raw_input"`
	OrgRole  string   `json:"org_role" binding:"required,oneof=OWNER ADMIN MEMBER"`
}

// BulkAddMembersResponse represents the response for bulk adding members
type BulkAddMembersResponse struct {
	Added    []string `json:"added"`
	NotFound []string `json:"not_found"`
}
