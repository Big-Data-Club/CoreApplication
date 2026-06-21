package dto

import "time"

// CreateShareLinkRequest is the request body for creating a project share link
type CreateShareLinkRequest struct {
	Role string `json:"role" binding:"required,oneof=editor reviewer viewer"`
}

// ShareLinkResponse is the response body for a share link record
type ShareLinkResponse struct {
	ID        int64      `json:"id"`
	ProjectID int64      `json:"project_id"`
	Token     string     `json:"token"`
	Role      string     `json:"role"`
	CreatedBy int64      `json:"created_by"`
	Active    bool       `json:"active"`
	ExpiresAt *time.Time `json:"expires_at,omitempty"`
	CreatedAt time.Time  `json:"created_at"`
	URL       string     `json:"url"` // full join URL, constructed server-side
}
