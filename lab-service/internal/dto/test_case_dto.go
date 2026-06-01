package dto

import "time"

type CreateTestCaseRequest struct {
	Name         string `json:"name" binding:"max=255"`
	OrderIndex   int    `json:"order_index" binding:"min=0"`
	IsSample     bool   `json:"is_sample"`
	IsHidden     bool   `json:"is_hidden"`
	Weight       int    `json:"weight" binding:"min=0"`
	Input        string `json:"input"`
	Expected     string `json:"expected"`
	TimeLimitMs  *int   `json:"time_limit_ms"`
	MemoryLimitMB *int  `json:"memory_limit_mb"`
	Explanation  string `json:"explanation"`
}

type UpdateTestCaseRequest struct {
	Name         *string `json:"name" binding:"omitempty,max=255"`
	OrderIndex   *int    `json:"order_index" binding:"omitempty,min=0"`
	IsSample     *bool   `json:"is_sample"`
	IsHidden     *bool   `json:"is_hidden"`
	Weight       *int    `json:"weight" binding:"omitempty,min=0"`
	Input        *string `json:"input"`
	Expected     *string `json:"expected"`
	TimeLimitMs  *int    `json:"time_limit_ms"`
	MemoryLimitMB *int   `json:"memory_limit_mb"`
	Explanation  *string `json:"explanation"`
}

type TestCaseResponse struct {
	ID            int64     `json:"id"`
	LabID         int64     `json:"lab_id"`
	Name          string    `json:"name"`
	OrderIndex    int       `json:"order_index"`
	IsSample      bool      `json:"is_sample"`
	IsHidden      bool      `json:"is_hidden"`
	Weight        int       `json:"weight"`
	Input         string    `json:"input,omitempty"`
	Expected      string    `json:"expected,omitempty"`
	TimeLimitMs   *int      `json:"time_limit_ms,omitempty"`
	MemoryLimitMB *int      `json:"memory_limit_mb,omitempty"`
	Explanation   string    `json:"explanation,omitempty"`
	CreatedAt     time.Time `json:"created_at"`
}

type BulkCreateTestCasesRequest struct {
	TestCases []CreateTestCaseRequest `json:"test_cases" binding:"required,min=1"`
}
