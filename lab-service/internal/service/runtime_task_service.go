package service

import (
	"context"
	"fmt"
	"net/http"
	"path/filepath"
	"strings"
	"time"

	"lab-service/internal/dto"
	"lab-service/internal/repository"
	"lab-service/internal/runtime"
)

type RuntimeTaskService struct {
	tasks    *repository.RuntimeTaskRepository
	labs     *repository.LabRepository
	enroll   *repository.EnrollmentRepository
	terminal *runtime.KubernetesTerminalSandbox
}

func NewRuntimeTaskService(tasks *repository.RuntimeTaskRepository, labs *repository.LabRepository, enroll *repository.EnrollmentRepository, terminal *runtime.KubernetesTerminalSandbox) *RuntimeTaskService {
	return &RuntimeTaskService{tasks: tasks, labs: labs, enroll: enroll, terminal: terminal}
}

func (s *RuntimeTaskService) Create(ctx context.Context, labID int64, req dto.CreateRuntimeTaskRequest) (*dto.RuntimeTaskResponse, int, error) {
	lab, err := s.labs.GetByID(ctx, labID)
	if err != nil {
		return nil, http.StatusNotFound, err
	}
	runtimeType := lab.LabType
	if runtimeType != "WORKSPACE" && runtimeType != "HPC" {
		return nil, http.StatusConflict, fmt.Errorf("runtime tasks are only supported for WORKSPACE and HPC labs")
	}
	if err := validateVerifier(runtimeType, req.VerifierType, req.VerifierConfig); err != nil {
		return nil, http.StatusBadRequest, err
	}
	out, err := s.tasks.Create(ctx, labID, runtimeType, req)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	return out, http.StatusCreated, nil
}
func (s *RuntimeTaskService) Delete(ctx context.Context, id int64) (int, error) {
	if err := s.tasks.Delete(ctx, id); err != nil {
		return http.StatusNotFound, err
	}
	return http.StatusOK, nil
}
func (s *RuntimeTaskService) Progress(ctx context.Context, labID, userID int64) (*dto.RuntimeTaskProgressResponse, int, error) {
	tasks, err := s.tasks.List(ctx, labID, userID, false)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	return buildProgress(tasks), http.StatusOK, nil
}
func (s *RuntimeTaskService) Check(ctx context.Context, labID, userID int64, session string) (*dto.RuntimeTaskProgressResponse, int, error) {
	enrolled, _ := s.enroll.IsEnrolled(ctx, labID, userID)
	if !enrolled {
		return nil, http.StatusForbidden, fmt.Errorf("not enrolled in this lab")
	}
	tasks, err := s.tasks.List(ctx, labID, userID, true)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	for _, task := range tasks {
		passed, message, evidence := false, "", map[string]interface{}{}
		if task.RuntimeType == "WORKSPACE" {
			if s.terminal == nil {
				return nil, http.StatusServiceUnavailable, fmt.Errorf("terminal sandbox unavailable")
			}
			if session == "" {
				return nil, http.StatusBadRequest, fmt.Errorf("session_id is required")
			}
			cmd, expected, err := verifierCommand(task)
			if err != nil {
				return nil, http.StatusBadRequest, err
			}
			checkCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
			output, ok, runErr := s.terminal.RunCommand(checkCtx, session, labID, userID, cmd)
			cancel()
			passed = ok
			if task.VerifierType == "COMMAND_OUTPUT" {
				passed = ok && strings.TrimSpace(output) == strings.TrimSpace(expected)
			}
			if runErr != nil {
				message = runErr.Error()
			} else if passed {
				message = "Đã hoàn thành"
			} else {
				message = "Chưa đạt yêu cầu"
			}
			evidence["output"] = output
		} else {
			status, hasJob, err := s.tasks.LatestHPCStatus(ctx, labID, userID)
			if err != nil {
				return nil, http.StatusInternalServerError, err
			}
			if task.VerifierType == "HPC_JOB_SUBMITTED" {
				passed = hasJob
			} else {
				passed = hasJob && (status == "COMPLETED" || status == "ACCEPTED")
			}
			if passed {
				message = "Đã hoàn thành"
			} else {
				message = "Chưa có HPC job phù hợp"
			}
			evidence["status"] = status
		}
		if err := s.tasks.SaveAttempt(ctx, task, userID, session, passed, message, evidence); err != nil {
			return nil, http.StatusInternalServerError, fmt.Errorf("failed to save task result: %w", err)
		}
	}
	latest, err := s.tasks.List(ctx, labID, userID, false)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	return buildProgress(latest), http.StatusOK, nil
}

func buildProgress(tasks []repository.RuntimeTask) *dto.RuntimeTaskProgressResponse {
	r := &dto.RuntimeTaskProgressResponse{Tasks: []dto.RuntimeTaskResponse{}, RequiredPassed: true}
	for _, t := range tasks {
		r.Tasks = append(r.Tasks, t.RuntimeTaskResponse)
		r.TotalWeight += t.Weight
		if t.Passed {
			r.PassedWeight += t.Weight
		}
		if t.IsRequired && !t.Passed {
			r.RequiredPassed = false
		}
	}
	if r.TotalWeight > 0 {
		r.Score = float64(r.PassedWeight) * 100 / float64(r.TotalWeight)
	}
	r.Completed = len(tasks) > 0 && r.RequiredPassed && r.Score >= 80
	return r
}
func validateVerifier(runtimeType, kind string, cfg map[string]interface{}) error {
	if runtimeType == "HPC" {
		if kind != "HPC_JOB_SUBMITTED" && kind != "HPC_JOB_COMPLETED" {
			return fmt.Errorf("invalid HPC verifier")
		}
		return nil
	}
	switch kind {
	case "FILE_EXISTS", "FILE_CONTAINS":
		p, _ := cfg["path"].(string)
		if p == "" || filepath.IsAbs(p) || strings.Contains(filepath.Clean(p), "..") {
			return fmt.Errorf("path must stay inside the workspace")
		}
		if kind == "FILE_CONTAINS" {
			contains, _ := cfg["contains"].(string)
			if contains == "" {
				return fmt.Errorf("contains text is required")
			}
		}
	case "COMMAND_EXIT", "COMMAND_OUTPUT":
		cmd, _ := cfg["command"].(string)
		if cmd == "" || len(cmd) > 2000 {
			return fmt.Errorf("command is required and limited to 2000 characters")
		}
	default:
		return fmt.Errorf("invalid WORKSPACE verifier")
	}
	return nil
}
func verifierCommand(t repository.RuntimeTask) (string, string, error) {
	q := func(v string) string { return "'" + strings.ReplaceAll(v, "'", "'\\''") + "'" }
	get := func(key string) (string, error) {
		v, ok := t.VerifierConfig[key].(string)
		if !ok || v == "" {
			return "", fmt.Errorf("invalid %s verifier configuration", key)
		}
		return v, nil
	}
	switch t.VerifierType {
	case "FILE_EXISTS":
		path, err := get("path")
		if err != nil {
			return "", "", err
		}
		return "test -e /workspace/" + q(path), "", nil
	case "FILE_CONTAINS":
		path, err := get("path")
		if err != nil {
			return "", "", err
		}
		contains, err := get("contains")
		if err != nil {
			return "", "", err
		}
		return "grep -Fq -- " + q(contains) + " /workspace/" + q(path), "", nil
	case "COMMAND_EXIT", "COMMAND_OUTPUT":
		cmd, err := get("command")
		if err != nil {
			return "", "", err
		}
		expected, _ := t.VerifierConfig["expected"].(string)
		return cmd, expected, nil
	}
	return "", "", fmt.Errorf("unsupported verifier")
}
