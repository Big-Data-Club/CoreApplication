package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"lab-service/internal/dto"
	"lab-service/internal/runtime"
	"strings"
	"time"
)

var ErrGeneratorUnavailable = errors.New("coding sandbox unavailable")

type GenerateTestCasesRequest struct {
	Language      string                      `json:"language" binding:"required"`
	GeneratorCode string                      `json:"generator_code" binding:"required,max=32768"`
	ReferenceCode string                      `json:"reference_code" binding:"required,max=32768"`
	Count         int                         `json:"count" binding:"required,min=1,max=50"`
	Seed          int64                       `json:"seed"`
	Samples       []dto.CreateTestCaseRequest `json:"samples" binding:"required,min=1,max=50,dive"`
}

// The generator receives one seed/index envelope per case; the existing bounded
// executor compiles once per batch. No teacher code runs in the API process.
func GenerateTestCases(ctx context.Context, adapter runtime.RuntimeAdapter, labID, userID int64, req GenerateTestCasesRequest) ([]dto.CreateTestCaseRequest, error) {
	switch req.Language {
	case "python", "cpp", "java", "go", "c", "rust", "scala":
	default:
		return nil, fmt.Errorf("unsupported generator language")
	}
	if req.Count < 1 || req.Count > 50 || len(req.Samples) < 1 || len(req.Samples) > 50 || len(req.GeneratorCode) > 32768 || len(req.ReferenceCode) > 32768 {
		return nil, fmt.Errorf("invalid generator bounds")
	}
	if err := dto.ValidateTestCases(req.Samples); err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(ctx, 9*time.Minute)
	defer cancel()
	run := func(code string, cases []runtime.TestCase) (*runtime.ExecutionResult, error) {
		result, err := adapter.Execute(ctx, runtime.ExecutionRequest{LabID: labID, UserID: userID, Language: req.Language, Code: code, TestCases: cases, RuntimeConfig: map[string]interface{}{"time_limit_ms": float64(2000), "memory_limit_mb": float64(256)}})
		if err != nil {
			return nil, fmt.Errorf("%w: %v", ErrGeneratorUnavailable, err)
		}
		return result, nil
	}
	samples := make([]runtime.TestCase, len(req.Samples))
	for i, c := range req.Samples {
		samples[i] = runtime.TestCase{ID: int64(i + 1), Input: c.Input, Expected: c.Expected, Weight: 1, TimeLimitMs: 2000, MemoryLimitMB: 256}
	}
	checked, err := run(req.ReferenceCode, samples)
	if err != nil {
		return nil, err
	}
	if checked == nil || checked.Status != "ACCEPTED" || checked.PassedTests != len(samples) {
		return nil, fmt.Errorf("reference solution does not pass the supplied samples; fix it before generating cases: %s", executionDiagnostic(checked))
	}
	inputs := make([]runtime.TestCase, req.Count)
	for i := range inputs {
		envelope, _ := json.Marshal(map[string]interface{}{"seed": req.Seed, "index": i, "count": req.Count})
		inputs[i] = runtime.TestCase{ID: int64(i + 1), Input: string(envelope), Weight: 1, TimeLimitMs: 2000, MemoryLimitMB: 256}
	}
	generated, err := run(req.GeneratorCode, inputs)
	if err != nil {
		return nil, err
	}
	if generated == nil || len(generated.TestResults) != req.Count {
		return nil, fmt.Errorf("generator did not produce the complete test set")
	}
	seen := map[string]bool{}
	for i, r := range generated.TestResults {
		if r.TestCaseID != inputs[i].ID || (r.Status != "PASSED" && r.Status != "WRONG_ANSWER") {
			return nil, fmt.Errorf("generator failed at case %d (%s)", i+1, r.Status)
		}
		value := strings.TrimSpace(r.ActualOutput)
		if value == "" || len(value) > 16384 || seen[value] {
			return nil, fmt.Errorf("generator case %d is empty, oversized or duplicated; adjust the generator/seed", i+1)
		}
		seen[value] = true
		inputs[i].Input = r.ActualOutput
	}
	oracle, err := run(req.ReferenceCode, inputs)
	if err != nil {
		return nil, err
	}
	if oracle == nil || len(oracle.TestResults) != req.Count {
		return nil, fmt.Errorf("reference solution did not produce all expected outputs")
	}
	cases := make([]dto.CreateTestCaseRequest, req.Count)
	for i, r := range oracle.TestResults {
		if r.TestCaseID != inputs[i].ID || (r.Status != "PASSED" && r.Status != "WRONG_ANSWER") {
			return nil, fmt.Errorf("reference solution failed at case %d (%s)", i+1, r.Status)
		}
		cases[i] = dto.CreateTestCaseRequest{Name: fmt.Sprintf("Generated %d (seed %d)", i+1, req.Seed), OrderIndex: i, IsHidden: true, Weight: 1, Input: inputs[i].Input, Expected: r.ActualOutput, Explanation: "Expected output computed by the teacher reference solution; review before saving."}
	}
	return cases, dto.ValidateTestCases(cases)
}

func executionDiagnostic(result *runtime.ExecutionResult) string {
	if result == nil {
		return "no execution result"
	}
	message := result.Status
	if result.CompilerOutput != "" {
		message += " · " + result.CompilerOutput
	}
	if len(message) > 2000 {
		message = message[:2000]
	}
	return message
}
