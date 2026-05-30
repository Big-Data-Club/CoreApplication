package dto

import "time"

// ── Submission DTOs ─────────────────────────────────────────────

// RunCodeRequest is used for "Run" (sample tests only, not graded).
type RunCodeRequest struct {
	Language string `json:"language" binding:"required"`
	Code     string `json:"code" binding:"required"`
}

// SubmitCodeRequest is used for "Submit" (all tests, graded).
type SubmitCodeRequest struct {
	Language string `json:"language" binding:"required"`
	Code     string `json:"code" binding:"required"`
}

// SubmitQueryRequest is for DATABASE labs.
type SubmitQueryRequest struct {
	Query string `json:"query" binding:"required"`
}

// SubmitJobRequest is for HPC labs.
type SubmitJobRequest struct {
	JobName       string `json:"job_name" binding:"max=255"`
	ScriptContent string `json:"script_content" binding:"required"`
	NumNodes      int    `json:"num_nodes" binding:"omitempty,min=1,max=100"`
	NumTasks      int    `json:"num_tasks" binding:"omitempty,min=1"`
	CpusPerTask   int    `json:"cpus_per_task" binding:"omitempty,min=1"`
	MemoryMB      int    `json:"memory_mb" binding:"omitempty,min=64"`
	GPUCount      int    `json:"gpu_count" binding:"omitempty,min=0"`
	MaxTime       string `json:"max_time" binding:"omitempty"`
}

// SubmissionResponse is the unified response for any submission type.
type SubmissionResponse struct {
	ID             int64                  `json:"id"`
	LabID          int64                  `json:"lab_id"`
	UserID         int64                  `json:"user_id"`
	Language       string                 `json:"language,omitempty"`
	Status         string                 `json:"status"`
	Score          float64                `json:"score"`
	MaxScore       float64                `json:"max_score"`
	PassedTests    int                    `json:"passed_tests"`
	TotalTests     int                    `json:"total_tests"`
	RuntimeMs      int                    `json:"runtime_ms"`
	MemoryKB       int                    `json:"memory_kb"`
	CompilerOutput string                 `json:"compiler_output,omitempty"`
	Feedback       map[string]interface{} `json:"feedback,omitempty"`
	SubmittedAt    time.Time              `json:"submitted_at"`
	GradedAt       *time.Time             `json:"graded_at,omitempty"`
}

// TestResultResponse is the per-test-case result.
type TestResultResponse struct {
	TestCaseID   int64  `json:"test_case_id"`
	TestName     string `json:"test_name"`
	Status       string `json:"status"`
	ActualOutput string `json:"actual_output,omitempty"`
	RuntimeMs    int    `json:"runtime_ms"`
	MemoryKB     int    `json:"memory_kb"`
	IsSample     bool   `json:"is_sample"`
}

// RunResultResponse is returned for "Run" (non-graded).
type RunResultResponse struct {
	TestResults    []TestResultResponse `json:"test_results"`
	CompilerOutput string               `json:"compiler_output,omitempty"`
	TotalRuntimeMs int                  `json:"total_runtime_ms"`
}
