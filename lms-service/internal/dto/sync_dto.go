package dto

// UserSyncRequest represents a single user sync request from auth service
type UserSyncRequest struct {
	UserID   int64    `json:"user_id" binding:"required"`
	Email    string   `json:"email" binding:"required,email"`
	FullName string   `json:"full_name" binding:"required"`
	Roles    []string `json:"roles" binding:"required,min=1"`
	Org      string   `json:"org" binding:"omitempty"`
}

// BulkUserSyncRequest represents bulk user sync request
type BulkUserSyncRequest struct {
	Users []UserSyncRequest `json:"users" binding:"required,min=1"`
}

// UserSyncResponse represents sync operation response
type UserSyncResponse struct {
	UserID        int64    `json:"user_id"`
	Email         string   `json:"email"`
	RolesAssigned []string `json:"roles_assigned"`
	IsNew         bool     `json:"is_new"`
}

// BulkUserSyncResponse represents bulk sync response
type BulkUserSyncResponse struct {
	TotalUsers    int                `json:"total_users"`
	SuccessCount  int                `json:"success_count"`
	FailedCount   int                `json:"failed_count"`
	SuccessUsers  []UserSyncResponse `json:"success_users"`
	FailedUsers   []SyncError        `json:"failed_users"`
}

// SyncError represents sync error for a user
type SyncError struct {
	UserID int64  `json:"user_id"`
	Email  string `json:"email"`
	Error  string `json:"error"`
}

// OrgSyncRequest represents an organization sync request from auth service
type OrgSyncRequest struct {
	ID          int64  `json:"id" binding:"required"`
	Name        string `json:"name" binding:"required"`
	Slug        string `json:"slug" binding:"required"`
	Description string `json:"description"`
	LogoURL     string `json:"logo_url"`
	IsActive    bool   `json:"is_active"`
	Settings    string `json:"settings" binding:"required"`
}

// OrgMemberSyncRequest represents an organization member sync request from auth service
type OrgMemberSyncRequest struct {
	OrgID   int64  `json:"org_id" binding:"required"`
	UserID  int64  `json:"user_id" binding:"required"`
	OrgRole string `json:"org_role" binding:"required"`
}