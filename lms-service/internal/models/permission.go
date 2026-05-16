package models

import "time"

// Permission represents a single grantable capability in the system.
type Permission struct {
	ID          int64     `json:"id" db:"id"`
	Code        string    `json:"code" db:"code"`
	Module      string    `json:"module" db:"module"`
	Description string    `json:"description" db:"description"`
	CreatedAt   time.Time `json:"created_at" db:"created_at"`
}

// RolePermission represents the N-N assignment of a permission to a role.
type RolePermission struct {
	RoleID       int64     `json:"role_id" db:"role_id"`
	PermissionID int64     `json:"permission_id" db:"permission_id"`
	AssignedAt   time.Time `json:"assigned_at" db:"assigned_at"`
}
