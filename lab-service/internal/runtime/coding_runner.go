package runtime

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

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
// Phase 1: simple local exec-based approach.
// Phase 2: actual sandboxed execution with K8s Jobs.
func executeTestCase(language, code string, tc TestCase, timeLimitMs, memoryLimitMB int) TestResult {
	_ = memoryLimitMB

	logger.Info(fmt.Sprintf("CodingRunner: executing test case %q (lang=%s, timeLimit=%dms, memLimit=%dMB)",
		tc.Name, language, timeLimitMs, memoryLimitMB))

	lang := strings.ToLower(language)

	// Create a temporary directory for code execution
	tempDir, err := os.MkdirTemp("", "bdc-sandbox-")
	if err != nil {
		return TestResult{
			TestCaseID:   tc.ID,
			Status:       "RUNTIME_ERROR",
			ActualOutput: fmt.Sprintf("Failed to create temporary sandbox directory: %v", err),
			RuntimeMs:    0,
		}
	}
	defer os.RemoveAll(tempDir)

	var sourceFile string
	var compileCmd *exec.Cmd
	var runCmd *exec.Cmd
	var isCompiled bool

	switch lang {
	case "python", "python3":
		sourceFile = filepath.Join(tempDir, "solution.py")
		if err := os.WriteFile(sourceFile, []byte(code), 0644); err != nil {
			return TestResult{TestCaseID: tc.ID, Status: "RUNTIME_ERROR", ActualOutput: err.Error()}
		}
		pyExe := "python3"
		if _, err := exec.LookPath("python3"); err != nil {
			if _, err2 := exec.LookPath("python"); err2 == nil {
				pyExe = "python"
			}
		}
		runCmd = exec.Command(pyExe, "solution.py")

	case "c":
		sourceFile = filepath.Join(tempDir, "solution.c")
		if err := os.WriteFile(sourceFile, []byte(code), 0644); err != nil {
			return TestResult{TestCaseID: tc.ID, Status: "RUNTIME_ERROR", ActualOutput: err.Error()}
		}
		isCompiled = true
		compileCmd = exec.Command("gcc", "-O2", "-o", "exec", "solution.c")
		runCmd = exec.Command("./exec")

	case "cpp", "c++":
		sourceFile = filepath.Join(tempDir, "solution.cpp")
		if err := os.WriteFile(sourceFile, []byte(code), 0644); err != nil {
			return TestResult{TestCaseID: tc.ID, Status: "RUNTIME_ERROR", ActualOutput: err.Error()}
		}
		isCompiled = true
		compileCmd = exec.Command("g++", "-O2", "-o", "exec", "solution.cpp")
		runCmd = exec.Command("./exec")

	case "java":
		sourceFile = filepath.Join(tempDir, "Main.java")
		if err := os.WriteFile(sourceFile, []byte(code), 0644); err != nil {
			return TestResult{TestCaseID: tc.ID, Status: "RUNTIME_ERROR", ActualOutput: err.Error()}
		}
		isCompiled = true
		compileCmd = exec.Command("javac", "Main.java")
		runCmd = exec.Command("java", "Main")

	case "go", "golang":
		sourceFile = filepath.Join(tempDir, "main.go")
		if err := os.WriteFile(sourceFile, []byte(code), 0644); err != nil {
			return TestResult{TestCaseID: tc.ID, Status: "RUNTIME_ERROR", ActualOutput: err.Error()}
		}
		isCompiled = true
		compileCmd = exec.Command("go", "build", "-o", "exec", "main.go")
		runCmd = exec.Command("./exec")

	case "rust", "rs":
		sourceFile = filepath.Join(tempDir, "main.rs")
		if err := os.WriteFile(sourceFile, []byte(code), 0644); err != nil {
			return TestResult{TestCaseID: tc.ID, Status: "RUNTIME_ERROR", ActualOutput: err.Error()}
		}
		isCompiled = true
		compileCmd = exec.Command("rustc", "-O", "-o", "exec", "main.rs")
		runCmd = exec.Command("./exec")

	case "scala":
		sourceFile = filepath.Join(tempDir, "Main.scala")
		if err := os.WriteFile(sourceFile, []byte(code), 0644); err != nil {
			return TestResult{TestCaseID: tc.ID, Status: "RUNTIME_ERROR", ActualOutput: err.Error()}
		}
		isCompiled = true
		compileCmd = exec.Command("scalac", "Main.scala")
		runCmd = exec.Command("scala", "Main")

	default:
		return TestResult{
			TestCaseID:   tc.ID,
			Status:       "RUNTIME_ERROR",
			ActualOutput: fmt.Sprintf("Unsupported programming language: %s", language),
		}
	}

	// Compilation step if required
	if isCompiled && compileCmd != nil {
		compileCmd.Dir = tempDir
		var compileStderr bytes.Buffer
		compileCmd.Stderr = &compileStderr
		var compileStdout bytes.Buffer
		compileCmd.Stdout = &compileStdout

		// Check if compiler exists
		if _, err := exec.LookPath(compileCmd.Path); err != nil {
			return TestResult{
				TestCaseID:   tc.ID,
				Status:       "COMPILER_ERROR",
				ActualOutput: fmt.Sprintf("Compiler %q is not installed on the system.", compileCmd.Args[0]),
				RuntimeMs:    0,
			}
		}

		compileCtx, compileCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer compileCancel()
		
		err := compileCmd.Run()
		if compileCtx.Err() == context.DeadlineExceeded {
			return TestResult{
				TestCaseID:   tc.ID,
				Status:       "COMPILER_ERROR",
				ActualOutput: "Compilation timed out (max 10s)",
			}
		}
		if err != nil {
			compilerOutput := compileStderr.String()
			if compilerOutput == "" {
				compilerOutput = compileStdout.String()
			}
			if compilerOutput == "" {
				compilerOutput = err.Error()
			}
			return TestResult{
				TestCaseID:   tc.ID,
				Status:       "COMPILER_ERROR",
				ActualOutput: compilerOutput,
			}
		}
	}

	// Execution Step
	if runCmd != nil {
		runCmd.Dir = tempDir
		runCmd.Stdin = bytes.NewBufferString(tc.Input)
		var stdout, stderr bytes.Buffer
		runCmd.Stdout = &stdout
		runCmd.Stderr = &stderr

		// Check if runner exists
		if _, err := exec.LookPath(runCmd.Path); err != nil {
			return TestResult{
				TestCaseID:   tc.ID,
				Status:       "RUNTIME_ERROR",
				ActualOutput: fmt.Sprintf("Runner/Interpreter %q is not installed on the system.", runCmd.Args[0]),
			}
		}

		startTime := time.Now()
		done := make(chan error, 1)
		go func() {
			done <- runCmd.Run()
		}()

		var runErr error
		select {
		case runErr = <-done:
			// Completed
		case <-time.After(time.Duration(timeLimitMs) * time.Millisecond):
			// Timeout
			if runCmd.Process != nil {
				runCmd.Process.Kill()
			}
			return TestResult{
				TestCaseID:   tc.ID,
				Status:       "TIME_LIMIT",
				ActualOutput: "Time Limit Exceeded",
				RuntimeMs:    timeLimitMs,
			}
		}

		duration := int(time.Since(startTime).Milliseconds())

		if runErr != nil {
			errStr := stderr.String()
			if errStr == "" {
				errStr = runErr.Error()
			}
			return TestResult{
				TestCaseID:   tc.ID,
				Status:       "RUNTIME_ERROR",
				ActualOutput: errStr,
				RuntimeMs:    duration,
			}
		}

		actualOutput := stdout.String()
		if CompareOutput(actualOutput, tc.Expected) {
			return TestResult{
				TestCaseID:   tc.ID,
				Status:       "PASSED",
				ActualOutput: actualOutput,
				RuntimeMs:    duration,
			}
		} else {
			return TestResult{
				TestCaseID:   tc.ID,
				Status:       "WRONG_ANSWER",
				ActualOutput: actualOutput,
				RuntimeMs:    duration,
			}
		}
	}

	return TestResult{
		TestCaseID:   tc.ID,
		Status:       "RUNTIME_ERROR",
		ActualOutput: "Failed to establish execution pipeline.",
	}
}

// CompareOutput compares actual and expected output for EXACT_MATCH.
func CompareOutput(actual, expected string) bool {
	a := strings.TrimRight(actual, " \t\n\r")
	e := strings.TrimRight(expected, " \t\n\r")
	return a == e
}
