package dto

// PermissionResponse is the API representation of a permission.
type PermissionResponse struct {
	ID          int64  `json:"id"`
	Code        string `json:"code"`
	Module      string `json:"module"`
	Description string `json:"description"`
}

// AssignPermissionsRequest is the body for PUT /admin/roles/:id/permissions.
type AssignPermissionsRequest struct {
	PermissionIDs []int64 `json:"permission_ids" binding:"required"`
}

// RolePermissionsResponse wraps the permissions currently assigned to a role.
type RolePermissionsResponse struct {
	RoleID      int64                `json:"role_id"`
	RoleName    string               `json:"role_name"`
	Permissions []PermissionResponse `json:"permissions"`
}
