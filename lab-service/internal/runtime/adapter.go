package runtime

import (
	"context"
	"fmt"
)

// RuntimeType identifies which execution backend to use.
type RuntimeType string

const (
	RuntimeCoding    RuntimeType = "CODING"
	RuntimeHPC       RuntimeType = "HPC"
	RuntimeJupyter   RuntimeType = "JUPYTER"
	RuntimeWorkspace RuntimeType = "WORKSPACE"
	RuntimeDatabase  RuntimeType = "DATABASE"
	RuntimeCustom    RuntimeType = "CUSTOM"
)

// TestCase passed to runtime for grading.
type TestCase struct {
	ID            int64
	Name          string
	Input         string
	Expected      string
	TimeLimitMs   int
	MemoryLimitMB int
	Weight        int
	IsSample      bool
}

// TestResult returned per test case after execution.
type TestResult struct {
	TestCaseID   int64
	Status       string // PASSED, WRONG_ANSWER, TIME_LIMIT, MEMORY_LIMIT, RUNTIME_ERROR
	ActualOutput string
	RuntimeMs    int
	MemoryKB     int
}

// ExecutionRequest is sent to any runtime adapter.
type ExecutionRequest struct {
	LabID         int64
	UserID        int64
	SubmissionID  int64
	RuntimeConfig map[string]interface{}

	// Coding-specific
	Language  string
	Code      string
	TestCases []TestCase

	// Database-specific
	Query     string
	SchemaSQL string
	SeedSQL   string

	// HPC-specific
	Script    string
	Resources map[string]interface{}
}

// ExecutionResult returned by runtime adapter.
type ExecutionResult struct {
	Status         string // ACCEPTED, WRONG_ANSWER, TIME_LIMIT, etc.
	Score          float64
	MaxScore       float64
	RuntimeMs      int
	MemoryKB       int
	PassedTests    int
	TotalTests     int
	TestResults    []TestResult
	CompilerOutput string
	Stdout         string
	Stderr         string
	ExitCode       int
	JobID          string // For async (HPC)
}

// RuntimeAdapter is implemented by each lab type backend.
type RuntimeAdapter interface {
	// Type returns the runtime type this adapter handles.
	Type() RuntimeType

	// Execute runs code/query synchronously (CODING, DATABASE).
	Execute(ctx context.Context, req ExecutionRequest) (*ExecutionResult, error)

	// Validate checks if runtime_config is valid for this type.
	Validate(config map[string]interface{}) error
}

// Registry maps RuntimeType to its adapter.
type Registry struct {
	adapters map[RuntimeType]RuntimeAdapter
}

func NewRegistry() *Registry {
	return &Registry{adapters: make(map[RuntimeType]RuntimeAdapter)}
}

func (r *Registry) Register(adapter RuntimeAdapter) {
	r.adapters[adapter.Type()] = adapter
}

func (r *Registry) Get(t RuntimeType) (RuntimeAdapter, error) {
	a, ok := r.adapters[t]
	if !ok {
		return nil, fmt.Errorf("unsupported runtime type: %s", t)
	}
	return a, nil
}
