package service

import (
	"context"
	"errors"
	"lab-service/internal/dto"
	"lab-service/internal/runtime"
	"strings"
	"testing"
)

type generatorAdapter struct {
	calls int
	mode  string
}

func (a *generatorAdapter) Type() runtime.RuntimeType             { return runtime.RuntimeCoding }
func (a *generatorAdapter) Validate(map[string]interface{}) error { return nil }
func (a *generatorAdapter) Execute(ctx context.Context, req runtime.ExecutionRequest) (*runtime.ExecutionResult, error) {
	a.calls++
	if _, ok := ctx.Deadline(); !ok {
		return nil, errors.New("missing deadline")
	}
	if a.mode == "infra" {
		return nil, errors.New("sandbox unavailable")
	}
	out := &runtime.ExecutionResult{Status: "ACCEPTED", PassedTests: len(req.TestCases)}
	for i, tc := range req.TestCases {
		value, status := "63", "PASSED"
		if a.calls == 1 && a.mode == "bad-sample" {
			out.Status = "WRONG_ANSWER"
			out.PassedTests = 0
		}
		if a.calls == 2 {
			value, status = string(rune('a'+i)), "WRONG_ANSWER"
			if a.mode == "duplicate" {
				value = "duplicate"
			}
			if a.mode == "runtime" {
				status = "RUNTIME_ERROR"
			}
		}
		if a.calls == 3 {
			status = "WRONG_ANSWER"
			if a.mode == "timeout" {
				status = "TIME_LIMIT"
			}
		}
		out.TestResults = append(out.TestResults, runtime.TestResult{TestCaseID: tc.ID, Status: status, ActualOutput: value})
	}
	return out, nil
}
func TestGenerateTestCasesOracleAndBounds(t *testing.T) {
	req := GenerateTestCasesRequest{Language: "python", GeneratorCode: "generator", ReferenceCode: "oracle", Count: 2, Seed: 42, Samples: []dto.CreateTestCaseRequest{{Input: "sample", Expected: "63"}}}
	for _, mode := range []string{"", "bad-sample", "duplicate", "runtime", "timeout", "infra"} {
		t.Run(mode, func(t *testing.T) {
			a := &generatorAdapter{mode: mode}
			cases, err := GenerateTestCases(context.Background(), a, 1, 2, req)
			if mode == "" {
				if err != nil || len(cases) != 2 || cases[0].Expected != "63" || !cases[0].IsHidden {
					t.Fatalf("invalid preview: %v %v", cases, err)
				}
				if a.calls != 3 {
					t.Fatalf("executions=%d", a.calls)
				}
			} else if err == nil {
				t.Fatal("unsafe generator accepted")
			}
			if mode == "bad-sample" && a.calls != 1 {
				t.Fatal("generation proceeded before oracle passed samples")
			}
		})
	}
	req.GeneratorCode = strings.Repeat("x", 32769)
	a := &generatorAdapter{}
	if _, err := GenerateTestCases(context.Background(), a, 1, 2, req); err == nil || a.calls != 0 {
		t.Fatal("oversized source executed")
	}
}
