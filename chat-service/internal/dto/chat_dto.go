package dto

import "time"

// ─── Channels ────────────────────────────────────────────────────────────────

type CreateChannelRequest struct {
	Slug        string `json:"slug"        binding:"required,min=2,max=80"`
	Name        string `json:"name"        binding:"required,min=2,max=120"`
	Description string `json:"description"`
	IsPrivate   bool   `json:"is_private"`
}

type UpdateChannelRequest struct {
	Name        string `json:"name"        binding:"required,min=2,max=120"`
	Description string `json:"description"`
	IsPrivate   bool   `json:"is_private"`
}

type UserResponse struct {
	ID             int64  `json:"id"`
	Email          string `json:"email"`
	FullName       string `json:"full_name"`
	ProfilePicture string `json:"profile_picture"`
}

type CreateDMRequest struct {
	UserID int64 `json:"user_id" binding:"required"`
}

type ChannelResponse struct {
	ID          int64         `json:"id"`
	Slug        string        `json:"slug"`
	Name        string        `json:"name"`
	Description string        `json:"description"`
	IsPrivate   bool          `json:"is_private"`
	IsDM        bool          `json:"is_dm"`
	DMUser      *UserResponse `json:"dm_user,omitempty"`
	CreatedAt   time.Time     `json:"created_at"`
}

// ─── Channel Role/User Access ─────────────────────────────────────────────────

type ChannelRoleEntry struct {
	RoleName string `json:"role_name" binding:"required"`
	CanRead  bool   `json:"can_read"`
	CanWrite bool   `json:"can_write"`
}

type SetChannelRolesRequest struct {
	Roles []ChannelRoleEntry `json:"roles" binding:"required"`
}

type SetChannelUsersRequest struct {
	UserIDs []int64 `json:"user_ids" binding:"required"`
}

// ChannelUsersResponse is returned by both GET and PUT /admin/channels/:id/users.
// It embeds full user objects so the caller never needs a second request.
type ChannelUsersResponse struct {
	Users []UserResponse `json:"users"`
}

// ─── Messages ─────────────────────────────────────────────────────────────────

type SendMessageRequest struct {
	Body string `json:"body" binding:"required,min=1,max=4000"`
}

type MessageResponse struct {
	ID           int64     `json:"id"`
	ChannelID    int64     `json:"channel_id"`
	SenderID     int64     `json:"sender_id"`
	SenderName   string    `json:"sender_name"`
	SenderEmail  string    `json:"sender_email"`
	SenderAvatar string    `json:"sender_avatar"`
	Body         string    `json:"body"`
	IsDeleted    bool      `json:"is_deleted"`
	CreatedAt    time.Time `json:"created_at"`
}

type MessageListResponse struct {
	Messages   []MessageResponse `json:"messages"`
	NextCursor int64             `json:"next_cursor"` // 0 = no more pages
	HasMore    bool              `json:"has_more"`
}

// ─── Users ────────────────────────────────────────────────────────────────────

type SyncUserRequest struct {
	ID             int64  `json:"id"              binding:"required"`
	Email          string `json:"email"           binding:"required,email"`
	FullName       string `json:"full_name"`
	ProfilePicture string `json:"profile_picture"`
}

type BulkSyncUsersRequest struct {
	Users []SyncUserRequest `json:"users" binding:"required"`
}

// ─── Admin ────────────────────────────────────────────────────────────────────

type AdminChannelResponse struct {
	ChannelResponse
	Roles []ChannelRoleEntry `json:"roles"`
	Users []int64            `json:"whitelisted_user_ids"`
}
