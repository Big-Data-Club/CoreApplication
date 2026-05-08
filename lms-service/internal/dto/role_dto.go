package dto

type RoleDefinitionRequest struct {
	Name        string `json:"name" binding:"required"`
	DisplayName string `json:"display_name" binding:"required"`
	Description string `json:"description"`
}

type AssignRoleRequest struct {
	Role string `json:"role" binding:"required"`
}
