package dto

import "time"

// AddCollaboratorRequest is the request body for adding a collaborator to a project
type AddCollaboratorRequest struct {
	Email string `json:"email" binding:"required,email"`
	Role  string `json:"role"  binding:"required,oneof=editor reviewer viewer"`
}

// UpdateCollaboratorRequest is the request body for changing a collaborator's role
type UpdateCollaboratorRequest struct {
	Role string `json:"role" binding:"required,oneof=editor reviewer viewer"`
}

// CollaboratorResponse is the response body for a collaborator record
type CollaboratorResponse struct {
	ID        int64     `json:"id"`
	ProjectID int64     `json:"project_id"`
	UserID    int64     `json:"user_id"`
	UserEmail string    `json:"user_email"`
	Role      string    `json:"role"`
	AddedBy   int64     `json:"added_by"`
	CreatedAt time.Time `json:"created_at"`
}
