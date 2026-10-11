package service

import (
	"strings"
	"testing"

	"lab-service/internal/dto"
	"lab-service/internal/repository"
)

func TestBuildRuntimeTaskProgress(t *testing.T) {
	tasks := []repository.RuntimeTask{
		{RuntimeTaskResponse: dto.RuntimeTaskResponse{Weight: 80, IsRequired: true, Passed: true}},
		{RuntimeTaskResponse: dto.RuntimeTaskResponse{Weight: 20, IsRequired: false, Passed: false}},
	}
	progress := buildProgress(tasks)
	if !progress.Completed || progress.Score != 80 || !progress.RequiredPassed {
		t.Fatalf("unexpected progress: %+v", progress)
	}
	tasks[0].Passed = false
	progress = buildProgress(tasks)
	if progress.Completed || progress.RequiredPassed {
		t.Fatalf("required task failure must prevent completion: %+v", progress)
	}
}

func TestValidateRuntimeTaskVerifier(t *testing.T) {
	valid := map[string]interface{}{"path": "results/output.txt", "contains": "PASS"}
	if err := validateVerifier("WORKSPACE", "FILE_CONTAINS", valid); err != nil {
		t.Fatalf("valid verifier rejected: %v", err)
	}
	for _, path := range []string{"/etc/passwd", "../secret", "results/../../secret"} {
		if err := validateVerifier("WORKSPACE", "FILE_EXISTS", map[string]interface{}{"path": path}); err == nil {
			t.Fatalf("unsafe path accepted: %s", path)
		}
	}
	if err := validateVerifier("HPC", "COMMAND_EXIT", map[string]interface{}{}); err == nil {
		t.Fatal("workspace verifier accepted for HPC")
	}
}

func TestVerifierCommandQuotesWorkspaceValues(t *testing.T) {
	task := repository.RuntimeTask{
		RuntimeTaskResponse: dto.RuntimeTaskResponse{VerifierType: "FILE_CONTAINS"},
		VerifierConfig:      map[string]interface{}{"path": "my file.txt", "contains": "it's ready"},
	}
	command, _, err := verifierCommand(task)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(command, "'it'\\''s ready'") || !strings.Contains(command, "'my file.txt'") {
		t.Fatalf("values were not safely quoted: %s", command)
	}
}

func TestRuntimeProgressRequiresAllMandatorySteps(t *testing.T) {
	tasks := []repository.RuntimeTask{{RuntimeTaskResponse: dto.RuntimeTaskResponse{Weight: 90, Passed: true}}, {RuntimeTaskResponse: dto.RuntimeTaskResponse{Weight: 10, IsRequired: true}}}
	if r := buildProgress(tasks); r.Score != 90 || r.Completed {
		t.Fatalf("missing mandatory step accepted: %+v", r)
	}
	tasks[1].Passed = true
	if r := buildProgress(tasks); !r.Completed || r.Score != 100 {
		t.Fatalf("completed steps rejected: %+v", r)
	}
	if buildProgress(nil).Completed {
		t.Fatal("empty rubric completed")
	}
}
func TestRuntimeVerifierBounds(t *testing.T) {
	for _, p := range []string{"../secret", "/etc/passwd", "a/../../secret"} {
		if validateVerifier("WORKSPACE", "FILE_EXISTS", map[string]interface{}{"path": p}) == nil {
			t.Fatalf("unsafe path %s", p)
		}
	}
	if err := validateVerifier("WORKSPACE", "FILE_EXISTS", map[string]interface{}{"path": "project/a..b"}); err != nil {
		t.Fatal(err)
	}
	if validateVerifier("WORKSPACE", "COMMAND_OUTPUT", map[string]interface{}{"command": "pwd"}) == nil {
		t.Fatal("missing expected output accepted")
	}
	if err := validateVerifier("WORKSPACE", "COMMAND_OUTPUT", map[string]interface{}{"command": "printf ''", "expected": ""}); err != nil {
		t.Fatal(err)
	}
}
