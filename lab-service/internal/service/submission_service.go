package service

import (
	"context"
	"fmt"
	"net/http"
	"strconv"

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
	unsafeLocalExecutionEnabled bool
}

func NewSubmissionService(
	subRepo *repository.SubmissionRepository,
	testCaseRepo *repository.TestCaseRepository,
	labRepo *repository.LabRepository,
	enrollRepo *repository.EnrollmentRepository,
	leaderboard *repository.LeaderboardRepository,
	registry *runtime.Registry,
	unsafeLocalExecutionEnabled bool,
) *SubmissionService {
	return &SubmissionService{
		subRepo: subRepo, testCaseRepo: testCaseRepo,
		labRepo: labRepo, enrollRepo: enrollRepo,
		leaderboard: leaderboard, registry: registry,
		unsafeLocalExecutionEnabled: unsafeLocalExecutionEnabled,
	}
}

// RunCode executes against sample test cases only (not graded, not recorded).
func (s *SubmissionService) RunCode(ctx context.Context, labID, userID int64, req *dto.RunCodeRequest) (*dto.RunResultResponse, int, error) {
	lab, err := s.labRepo.GetByID(ctx, labID)
	if err != nil {
		return nil, http.StatusNotFound, fmt.Errorf("lab not found")
	}
	if lab.LabType == "CODING" && !s.unsafeLocalExecutionEnabled {
		return nil, http.StatusServiceUnavailable, fmt.Errorf("coding sandbox is being provisioned; execution is temporarily unavailable")
	}
	if lab.LabType == "HPC" {
		return nil, http.StatusConflict, fmt.Errorf("HPC labs use batch-job submission, not the code-run endpoint")
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
	resp := &dto.RunResultResponse{CompilerOutput: result.CompilerOutput, TotalRuntimeMs: result.RuntimeMs, Status: result.Status}
	testCasesByID := make(map[int64]runtime.TestCase, len(runtimeTCs))
	for _, tc := range runtimeTCs {
		testCasesByID[tc.ID] = tc
	}
	for _, tr := range result.TestResults {
		resp.TestResults = append(resp.TestResults, learnerTestResult(tr, testCasesByID[tr.TestCaseID]))
	}
	return resp, http.StatusOK, nil
}

// SubmitCode executes against ALL test cases, records submission, updates leaderboard.
func (s *SubmissionService) SubmitCode(ctx context.Context, labID, userID int64, req *dto.SubmitCodeRequest) (*dto.SubmissionResponse, int, error) {
	lab, err := s.labRepo.GetByID(ctx, labID)
	if err != nil {
		return nil, http.StatusNotFound, fmt.Errorf("lab not found")
	}
	if lab.LabType == "CODING" && !s.unsafeLocalExecutionEnabled {
		return nil, http.StatusServiceUnavailable, fmt.Errorf("coding sandbox is being provisioned; submissions are temporarily unavailable")
	}
	if lab.LabType == "HPC" {
		return nil, http.StatusConflict, fmt.Errorf("HPC labs require the dedicated job-submission endpoint")
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
	// A graded submission may contain hidden tests. Return only sample-test
	// details so students can learn from feedback without revealing evaluation
	// inputs, expected outputs, or hidden-test-derived program output.
	testCasesByID := make(map[int64]runtime.TestCase, len(runtimeTCs))
	publicSampleByID := make(map[int64]bool, len(testCases))
	for _, tc := range runtimeTCs {
		testCasesByID[tc.ID] = tc
	}
	for _, tc := range testCases {
		publicSampleByID[tc.ID] = tc.IsSample && !tc.IsHidden
	}
	for _, tr := range result.TestResults {
		tc := testCasesByID[tr.TestCaseID]
		if publicSampleByID[tr.TestCaseID] {
			resp.TestResults = append(resp.TestResults, learnerTestResult(tr, tc))
		}
	}
	return resp, http.StatusOK, nil
}

// learnerTestResult is the safe diagnostic view exposed to a learner. It is
// used only for sample tests; hidden test data must never leave the API.
func learnerTestResult(result runtime.TestResult, testCase runtime.TestCase) dto.TestResultResponse {
	response := dto.TestResultResponse{
		TestCaseID:     result.TestCaseID,
		TestName:       testCase.Name,
		Status:         result.Status,
		Input:          testCase.Input,
		ExpectedOutput: testCase.Expected,
		RuntimeMs:      result.RuntimeMs,
		MemoryKB:       result.MemoryKB,
		IsSample:       true,
	}
	switch result.Status {
	case "COMPILER_ERROR", "RUNTIME_ERROR", "TIME_LIMIT", "MEMORY_LIMIT":
		response.ErrorOutput = result.ActualOutput
	default:
		response.ActualOutput = result.ActualOutput
	}
	return response
}

// SubmitHPCJob submits one bounded Slurm job. The job only receives resource
// values that the lab owner already constrained in runtime_config.
func (s *SubmissionService) SubmitHPCJob(ctx context.Context, labID, userID int64, req *dto.SubmitJobRequest) (*dto.SubmissionResponse, int, error) {
	lab, err := s.labRepo.GetByID(ctx, labID)
	if err != nil {
		return nil, http.StatusNotFound, fmt.Errorf("lab not found")
	}
	if lab.LabType != "HPC" {
		return nil, http.StatusConflict, fmt.Errorf("this endpoint is only available for HPC labs")
	}
	enrolled, _ := s.enrollRepo.IsEnrolled(ctx, labID, userID)
	if !enrolled {
		return nil, http.StatusForbidden, fmt.Errorf("not enrolled in this lab")
	}
	if lab.MaxSubmissions != nil && *lab.MaxSubmissions > 0 {
		count, _ := s.subRepo.CountByLabAndUser(ctx, labID, userID)
		if count >= *lab.MaxSubmissions {
			return nil, http.StatusTooManyRequests, fmt.Errorf("submission limit reached")
		}
	}
	adapter, err := s.registry.Get(runtime.RuntimeHPC)
	if err != nil {
		return nil, http.StatusServiceUnavailable, err
	}
	if err := adapter.Validate(lab.RuntimeConfig); err != nil {
		return nil, http.StatusServiceUnavailable, fmt.Errorf("HPC scheduler is not ready: %w", err)
	}

	submissionID, err := s.subRepo.Create(ctx, labID, userID, "SLURM", "", "", req.ScriptContent)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("failed to create HPC submission: %w", err)
	}
	result, err := adapter.Execute(ctx, runtime.ExecutionRequest{
		LabID: labID, UserID: userID, SubmissionID: submissionID, RuntimeConfig: lab.RuntimeConfig,
		Script: req.ScriptContent,
		Resources: map[string]interface{}{
			"job_name": req.JobName, "num_nodes": req.NumNodes, "num_tasks": req.NumTasks,
			"cpus_per_task": req.CpusPerTask, "memory_mb": req.MemoryMB, "gpu_count": req.GPUCount,
			"max_time": req.MaxTime,
		},
	})
	if err != nil {
		_ = s.subRepo.MarkHPCFailed(ctx, submissionID, err.Error())
		return nil, http.StatusBadGateway, fmt.Errorf("HPC job was not submitted: %w", err)
	}
	jobID, parseErr := parsePositiveID(result.JobID)
	if parseErr != nil {
		_ = s.subRepo.MarkHPCFailed(ctx, submissionID, "scheduler returned an invalid job ID")
		return nil, http.StatusBadGateway, fmt.Errorf("scheduler returned an invalid job ID")
	}
	if err := s.subRepo.MarkHPCSubmitted(ctx, submissionID, jobID); err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("failed to record scheduler job: %w", err)
	}
	resp, err := s.subRepo.GetByID(ctx, submissionID)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	return resp, http.StatusAccepted, nil
}

func parsePositiveID(value string) (int64, error) {
	id, err := strconv.ParseInt(value, 10, 64)
	if err != nil || id < 1 {
		return 0, fmt.Errorf("invalid ID")
	}
	return id, nil
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
