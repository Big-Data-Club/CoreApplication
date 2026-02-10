package dto

// UserRolesResponse represents the response for user roles
type UserRolesResponse struct {
	UserID int64    `json:"user_id"`
	Email  string   `json:"email"`
	Roles  []string `json:"roles"`
}