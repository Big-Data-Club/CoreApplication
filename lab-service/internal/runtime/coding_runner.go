package runtime

import (
	"context"
	"fmt"
	"strings"

	"lab-service/pkg/logger"
)

// CodingRunner executes code in a sandboxed environment and compares output.
// Phase 1 uses a simple exec-based approach. Phase 2 will use K8s Jobs + gVisor.
type CodingRunner struct{}

func NewCodingRunner() *CodingRunner {
	return &CodingRunner{}
}

func (r *CodingRunner) Type() RuntimeType {
	return RuntimeCoding
}

func (r *CodingRunner) Validate(config map[string]interface{}) error {
	if _, ok := config["supported_languages"]; !ok {
		return fmt.Errorf("coding runtime requires 'supported_languages' in config")
	}
	return nil
}

// Execute runs the submitted code against all test cases and returns results.
// In Phase 1, this is a placeholder that simulates execution.
// In Phase 2, this creates a K8s Job with gVisor/nsjail sandbox.
func (r *CodingRunner) Execute(ctx context.Context, req ExecutionRequest) (*ExecutionResult, error) {
	logger.Info(fmt.Sprintf("CodingRunner: executing %s code for submission %d with %d test cases",
		req.Language, req.SubmissionID, len(req.TestCases)))

	// Get time/memory limits from runtime config
	timeLimitMs := 2000
	if v, ok := req.RuntimeConfig["time_limit_ms"]; ok {
		if f, ok := v.(float64); ok {
			timeLimitMs = int(f)
		}
	}
	memoryLimitMB := 256
	if v, ok := req.RuntimeConfig["memory_limit_mb"]; ok {
		if f, ok := v.(float64); ok {
			memoryLimitMB = int(f)
		}
	}

	result := &ExecutionResult{
		TotalTests: len(req.TestCases),
		MaxScore:   100,
	}

	totalWeight := 0
	passedWeight := 0
	totalRuntime := 0

	for _, tc := range req.TestCases {
		tl := timeLimitMs
		if tc.TimeLimitMs > 0 {
			tl = tc.TimeLimitMs
		}
		ml := memoryLimitMB
		if tc.MemoryLimitMB > 0 {
			ml = tc.MemoryLimitMB
		}

		// Phase 1: Delegate to sandbox executor
		// Phase 2: K8s Job with gVisor
		tr := executeTestCase(req.Language, req.Code, tc, tl, ml)
		result.TestResults = append(result.TestResults, tr)

		totalWeight += tc.Weight
		if tr.Status == "PASSED" {
			result.PassedTests++
			passedWeight += tc.Weight
		}
		totalRuntime += tr.RuntimeMs
	}

	result.RuntimeMs = totalRuntime

	// Determine overall status
	if result.PassedTests == result.TotalTests {
		result.Status = "ACCEPTED"
	} else {
		// Find first non-passing status
		for _, tr := range result.TestResults {
			if tr.Status != "PASSED" {
				result.Status = tr.Status
				break
			}
		}
	}

	// Calculate score based on weights
	if totalWeight > 0 {
		result.Score = float64(passedWeight) / float64(totalWeight) * result.MaxScore
	}

	return result, nil
}

// executeTestCase runs a single test case against the code.
// Phase 1: placeholder that compares expected output.
// Phase 2: actual sandboxed execution.
func executeTestCase(language, code string, tc TestCase, timeLimitMs, memoryLimitMB int) TestResult {
	_ = timeLimitMs
	_ = memoryLimitMB

	// TODO: Phase 2 — Create K8s Job with code-runner image
	// For now, return a placeholder that marks all tests as PENDING
	// The actual execution will be done by the code-runner container

	logger.Info(fmt.Sprintf("CodingRunner: would execute test case %q (lang=%s, timeLimit=%dms, memLimit=%dMB)",
		tc.Name, language, timeLimitMs, memoryLimitMB))

	return TestResult{
		TestCaseID:   tc.ID,
		Status:       "PENDING",
		ActualOutput: "",
		RuntimeMs:    0,
		MemoryKB:     0,
	}
}

// CompareOutput compares actual and expected output for EXACT_MATCH.
func CompareOutput(actual, expected string) bool {
	// Trim trailing whitespace/newlines from both
	a := strings.TrimRight(actual, " \t\n\r")
	e := strings.TrimRight(expected, " \t\n\r")
	return a == e
}
