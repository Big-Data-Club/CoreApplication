package service

import (
	"context"
	"fmt"
	"net/http"

	"lab-service/internal/dto"
	"lab-service/internal/repository"
	"lab-service/internal/runtime"
	"lab-service/pkg/logger"
)

type SubmissionService struct {
	subRepo      *repository.SubmissionRepository
	testCaseRepo *repository.TestCaseRepository
	labRepo      *repository.LabRepository
	enrollRepo   *repository.EnrollmentRepository
	leaderboard  *repository.LeaderboardRepository
	registry     *runtime.Registry
}

func NewSubmissionService(
	subRepo *repository.SubmissionRepository,
	testCaseRepo *repository.TestCaseRepository,
	labRepo *repository.LabRepository,
	enrollRepo *repository.EnrollmentRepository,
	leaderboard *repository.LeaderboardRepository,
	registry *runtime.Registry,
) *SubmissionService {
	return &SubmissionService{
		subRepo: subRepo, testCaseRepo: testCaseRepo,
		labRepo: labRepo, enrollRepo: enrollRepo,
		leaderboard: leaderboard, registry: registry,
	}
}

// RunCode executes against sample test cases only (not graded, not recorded).
func (s *SubmissionService) RunCode(ctx context.Context, labID, userID int64, req *dto.RunCodeRequest) (*dto.RunResultResponse, int, error) {
	lab, err := s.labRepo.GetByID(ctx, labID)
	if err != nil {
		return nil, http.StatusNotFound, fmt.Errorf("lab not found")
	}

	// Get sample test cases only
	testCases, err := s.testCaseRepo.ListByLab(ctx, labID, true)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("failed to get test cases: %w", err)
	}

	// Build runtime request
	adapter, err := s.registry.Get(runtime.RuntimeType(lab.LabType))
	if err != nil {
		return nil, http.StatusBadRequest, err
	}

	runtimeTCs := make([]runtime.TestCase, len(testCases))
	for i, tc := range testCases {
		runtimeTCs[i] = runtime.TestCase{
			ID: tc.ID, Name: tc.Name,
			Input: tc.Input, Expected: tc.Expected,
			Weight: tc.Weight, IsSample: tc.IsSample,
		}
		if tc.TimeLimitMs != nil {
			runtimeTCs[i].TimeLimitMs = *tc.TimeLimitMs
		}
		if tc.MemoryLimitMB != nil {
			runtimeTCs[i].MemoryLimitMB = *tc.MemoryLimitMB
		}
	}

	result, err := adapter.Execute(ctx, runtime.ExecutionRequest{
		LabID: labID, UserID: userID,
		Language: req.Language, Code: req.Code,
		TestCases: runtimeTCs, RuntimeConfig: lab.RuntimeConfig,
	})
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("execution failed: %w", err)
	}

	// Build response
	resp := &dto.RunResultResponse{CompilerOutput: result.CompilerOutput, TotalRuntimeMs: result.RuntimeMs}
	for _, tr := range result.TestResults {
		resp.TestResults = append(resp.TestResults, dto.TestResultResponse{
			TestCaseID: tr.TestCaseID, Status: tr.Status,
			ActualOutput: tr.ActualOutput, RuntimeMs: tr.RuntimeMs,
			MemoryKB: tr.MemoryKB, IsSample: true,
		})
	}
	return resp, http.StatusOK, nil
}

// SubmitCode executes against ALL test cases, records submission, updates leaderboard.
func (s *SubmissionService) SubmitCode(ctx context.Context, labID, userID int64, req *dto.SubmitCodeRequest) (*dto.SubmissionResponse, int, error) {
	lab, err := s.labRepo.GetByID(ctx, labID)
	if err != nil {
		return nil, http.StatusNotFound, fmt.Errorf("lab not found")
	}

	// Check enrollment
	enrolled, _ := s.enrollRepo.IsEnrolled(ctx, labID, userID)
	if !enrolled {
		return nil, http.StatusForbidden, fmt.Errorf("not enrolled in this lab")
	}

	// Check submission limit
	if lab.MaxSubmissions != nil && *lab.MaxSubmissions > 0 {
		count, _ := s.subRepo.CountByLabAndUser(ctx, labID, userID)
		if count >= *lab.MaxSubmissions {
			return nil, http.StatusTooManyRequests, fmt.Errorf("submission limit reached")
		}
	}

	// Create submission record
	subID, err := s.subRepo.Create(ctx, labID, userID, req.Language, req.Code, "", "")
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("failed to create submission: %w", err)
	}

	// Get ALL test cases
	testCases, err := s.testCaseRepo.ListByLab(ctx, labID, false)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("failed to get test cases: %w", err)
	}

	// Build runtime request
	adapter, err := s.registry.Get(runtime.RuntimeType(lab.LabType))
	if err != nil {
		return nil, http.StatusBadRequest, err
	}

	runtimeTCs := make([]runtime.TestCase, len(testCases))
	for i, tc := range testCases {
		runtimeTCs[i] = runtime.TestCase{
			ID: tc.ID, Name: tc.Name,
			Input: tc.Input, Expected: tc.Expected,
			Weight: tc.Weight, IsSample: tc.IsSample,
		}
		if tc.TimeLimitMs != nil {
			runtimeTCs[i].TimeLimitMs = *tc.TimeLimitMs
		}
		if tc.MemoryLimitMB != nil {
			runtimeTCs[i].MemoryLimitMB = *tc.MemoryLimitMB
		}
	}

	result, err := adapter.Execute(ctx, runtime.ExecutionRequest{
		LabID: labID, UserID: userID, SubmissionID: subID,
		Language: req.Language, Code: req.Code,
		TestCases: runtimeTCs, RuntimeConfig: lab.RuntimeConfig,
	})
	if err != nil {
		s.subRepo.UpdateStatus(ctx, subID, "FAILED", 0, 0, len(testCases), 0, 0, err.Error())
		return nil, http.StatusInternalServerError, fmt.Errorf("execution failed: %w", err)
	}

	// Save test results
	for _, tr := range result.TestResults {
		s.subRepo.InsertTestResult(ctx, subID, tr.TestCaseID, tr.Status, tr.ActualOutput, tr.RuntimeMs, tr.MemoryKB)
	}

	// Update submission
	s.subRepo.UpdateStatus(ctx, subID, result.Status, result.Score,
		result.PassedTests, result.TotalTests, result.RuntimeMs, result.MemoryKB, result.CompilerOutput)

	// Update leaderboard
	if result.Status == "ACCEPTED" {
		s.leaderboard.UpsertEntry(ctx, labID, userID, subID, result.Score, result.RuntimeMs, result.MemoryKB)
	}

	logger.Info(fmt.Sprintf("Submission %d: %s (score=%.1f, %d/%d tests)",
		subID, result.Status, result.Score, result.PassedTests, result.TotalTests))

	// Get and return full response
	resp, err := s.subRepo.GetByID(ctx, subID)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	return resp, http.StatusOK, nil
}

// GetSubmission returns a submission with test results.
func (s *SubmissionService) GetSubmission(ctx context.Context, subID int64) (*dto.SubmissionResponse, int, error) {
	resp, err := s.subRepo.GetByID(ctx, subID)
	if err != nil {
		return nil, http.StatusNotFound, fmt.Errorf("submission not found")
	}
	return resp, http.StatusOK, nil
}

// ListMySubmissions returns user's submissions for a lab.
func (s *SubmissionService) ListMySubmissions(ctx context.Context, labID, userID int64, page, pageSize int) (*dto.ListResponse, int, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 50 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize

	subs, total, err := s.subRepo.ListByLabAndUser(ctx, labID, userID, pageSize, offset)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	if subs == nil {
		subs = []dto.SubmissionResponse{}
	}
	return dto.NewListResponse(subs, page, pageSize, total), http.StatusOK, nil
}
