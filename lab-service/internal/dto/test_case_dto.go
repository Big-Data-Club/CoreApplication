package dto

import (
	"fmt"
	"time"
)

type CreateTestCaseRequest struct {
	Name          string `json:"name" binding:"max=255"`
	OrderIndex    int    `json:"order_index" binding:"min=0"`
	IsSample      bool   `json:"is_sample"`
	IsHidden      bool   `json:"is_hidden"`
	Weight        int    `json:"weight" binding:"min=0"`
	Input         string `json:"input"`
	Expected      string `json:"expected"`
	TimeLimitMs   *int   `json:"time_limit_ms"`
	MemoryLimitMB *int   `json:"memory_limit_mb"`
	Explanation   string `json:"explanation"`
}

type UpdateTestCaseRequest struct {
	Name          *string `json:"name" binding:"omitempty,max=255"`
	OrderIndex    *int    `json:"order_index" binding:"omitempty,min=0"`
	IsSample      *bool   `json:"is_sample"`
	IsHidden      *bool   `json:"is_hidden"`
	Weight        *int    `json:"weight" binding:"omitempty,min=0"`
	Input         *string `json:"input"`
	Expected      *string `json:"expected"`
	TimeLimitMs   *int    `json:"time_limit_ms"`
	MemoryLimitMB *int    `json:"memory_limit_mb"`
	Explanation   *string `json:"explanation"`
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
	TestCases []CreateTestCaseRequest `json:"test_cases" binding:"required,min=1,max=50,dive"`
}

// ValidateTestCases mirrors the bounded execution contract before persistence.
func ValidateTestCases(cases []CreateTestCaseRequest) error {
	if len(cases) < 1 || len(cases) > 50 {
		return fmt.Errorf("a test suite must contain 1–50 cases")
	}
	for i, c := range cases {
		if len(c.Input) > 16384 || len(c.Expected) > 8192 || len(c.Name) > 255 || len(c.Explanation) > 2000 || c.OrderIndex < 0 || c.Weight < 0 || c.Weight > 1000 {
			return fmt.Errorf("test case %d exceeds the execution limits", i+1)
		}
		if c.IsSample && c.IsHidden {
			return fmt.Errorf("test case %d cannot be both sample and hidden", i+1)
		}
		if c.TimeLimitMs != nil && (*c.TimeLimitMs < 1 || *c.TimeLimitMs > 10000) {
			return fmt.Errorf("time limit must be 1–10000 ms")
		}
		if c.MemoryLimitMB != nil && (*c.MemoryLimitMB < 16 || *c.MemoryLimitMB > 1024) {
			return fmt.Errorf("memory limit must be 16–1024 MB")
		}
	}
	return nil
}

type ReplaceTestCasesRequest struct {
	ExpectedRevision string                  `json:"expected_revision" binding:"required"`
	ExpectedIDs      []int64                 `json:"expected_ids"`
	TestCases        []CreateTestCaseRequest `json:"test_cases" binding:"required,min=1,max=50,dive"`
}
