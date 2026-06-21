package dto

import "time"

type CreateProjectRequest struct {
	Title       string `json:"title" binding:"required,min=1,max=255"`
	Description string `json:"description" binding:"max=1000"`
	Compiler    string `json:"compiler" binding:"omitempty,oneof=pdflatex xelatex lualatex"`
	TemplateID  string `json:"template_id" binding:"omitempty"`
}

type UpdateProjectRequest struct {
	Title       *string `json:"title" binding:"omitempty,min=1,max=255"`
	Description *string `json:"description" binding:"omitempty,max=1000"`
	Compiler    *string `json:"compiler" binding:"omitempty,oneof=pdflatex xelatex lualatex"`
	MainFile    *string `json:"main_file" binding:"omitempty,min=1,max=255"`
}

type ProjectResponse struct {
	ID          int64      `json:"id"`
	UserID      int64      `json:"user_id"`
	Title       string     `json:"title"`
	Description string     `json:"description"`
	Compiler    string     `json:"compiler"`
	MainFile    string     `json:"main_file"`
	TemplateID  *string    `json:"template_id,omitempty"`
	Status      string     `json:"status"`
	CreatedAt   time.Time  `json:"created_at"`
	UpdatedAt   time.Time  `json:"updated_at"`
	UserRole    string     `json:"user_role,omitempty"` // "owner", "editor", "reviewer", "viewer"
}
