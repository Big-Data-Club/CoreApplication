package dto

type CreateRuntimeTaskRequest struct {
	Title          string                 `json:"title" binding:"required,min=3,max=255"`
	Description    string                 `json:"description" binding:"max=2000"`
	VerifierType   string                 `json:"verifier_type" binding:"required"`
	VerifierConfig map[string]interface{} `json:"verifier_config" binding:"required"`
	Weight         int                    `json:"weight" binding:"required,min=1,max=1000"`
	IsRequired     bool                   `json:"is_required"`
	OrderIndex     int                    `json:"order_index" binding:"min=0"`
}

type RuntimeTaskResponse struct {
	ID           int64  `json:"id"`
	LabID        int64  `json:"lab_id"`
	Title        string `json:"title"`
	Description  string `json:"description"`
	VerifierType string `json:"verifier_type,omitempty"`
	Weight       int    `json:"weight"`
	IsRequired   bool   `json:"is_required"`
	OrderIndex   int    `json:"order_index"`
	Passed       bool   `json:"passed"`
	LastMessage  string `json:"last_message,omitempty"`
}

type CheckRuntimeTasksRequest struct {
	SessionID string `json:"session_id"`
}
type RuntimeTaskProgressResponse struct {
	Tasks          []RuntimeTaskResponse `json:"tasks"`
	Score          float64               `json:"score"`
	PassedWeight   int                   `json:"passed_weight"`
	TotalWeight    int                   `json:"total_weight"`
	RequiredPassed bool                  `json:"required_passed"`
	Completed      bool                  `json:"completed"`
}
