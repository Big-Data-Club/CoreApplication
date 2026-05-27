package models

import (
	"database/sql"
	"encoding/json"
	"time"
)

// Organization represents an organization in the system
type Organization struct {
	ID          int64           `json:"id" db:"id"`
	Name        string          `json:"name" db:"name"`
	Slug        string          `json:"slug" db:"slug"`
	Description sql.NullString  `json:"description" db:"description"`
	LogoURL     sql.NullString  `json:"logo_url" db:"logo_url"`
	IsActive    bool            `json:"is_active" db:"is_active"`
	Settings    json.RawMessage `json:"settings" db:"settings"` // Unmarshals to OrgSettings
	CreatedBy   sql.NullInt64   `json:"created_by" db:"created_by"`
	CreatedAt   time.Time       `json:"created_at" db:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at" db:"updated_at"`
}

// OrgSettings represents configuration settings for an organization
type OrgSettings struct {
	AllowCrossOrgCourses    bool   `json:"allow_cross_org_courses"`
	DefaultCourseVisibility string `json:"default_course_visibility"`
	AllowSelfEnrollment     bool   `json:"allow_self_enrollment"`
	MaxMembers              int    `json:"max_members,omitempty"`
}

// OrgMember represents membership of a user in an organization
type OrgMember struct {
	ID       int64     `json:"id" db:"id"`
	OrgID    int64     `json:"org_id" db:"org_id"`
	UserID   int64     `json:"user_id" db:"user_id"`
	OrgRole  string    `json:"org_role" db:"org_role"`
	JoinedAt time.Time `json:"joined_at" db:"joined_at"`
}

// OrgMemberWithUserInfo includes basic user info for display
type OrgMemberWithUserInfo struct {
	UserID   int64     `json:"user_id" db:"user_id"`
	FullName string    `json:"full_name" db:"full_name"`
	Email    string    `json:"email" db:"email"`
	OrgRole  string    `json:"org_role" db:"org_role"`
	JoinedAt time.Time `json:"joined_at" db:"joined_at"`
}

// OrgStats represents aggregated statistics for an organization
type OrgStats struct {
	OrgID         int64 `json:"org_id"`
	MemberCount   int   `json:"member_count"`
	CourseCount   int   `json:"course_count"`
	EnrolledCount int   `json:"enrolled_count"`
}

// OrgRole constants
const (
	OrgRoleOwner  = "OWNER"
	OrgRoleAdmin  = "ADMIN"
	OrgRoleMember = "MEMBER"
)

// Course visibility constants
const (
	VisibilityPublic  = "PUBLIC"
	VisibilityOrgOnly = "ORG_ONLY"
)
