package dto

// UserSyncRequest represents a single user sync request from auth service
type UserSyncRequest struct {
	UserID   int64    `json:"user_id" binding:"required"`
	Email    string   `json:"email" binding:"required,email"`
	FullName string   `json:"full_name" binding:"required"`
	Roles    []string `json:"roles" binding:"required,min=1"`
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