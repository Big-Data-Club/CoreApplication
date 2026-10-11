package runtime

import (
	"context"
	"encoding/base64"
	"fmt"
	"strconv"
	"strings"
	"time"
)

const maxBatchTests = 50
const maxBatchLogBytes = 600 * 1024
const maxCaseOutputBytes = 8192

// Execute amortizes scheduling and compilation across tests with the same
// memory cap. Distinct caps retain separate cgroup limits, rather than silently
// increasing a test's memory allowance. Expected answers stay in the API.
func (e *KubernetesCodingExecutor) Execute(ctx context.Context, req ExecutionRequest) (*ExecutionResult, error) {
	ctx, executionCancel := context.WithTimeout(ctx, 9*time.Minute)
	defer executionCancel()
	release, err := acquireExecutionSlot(ctx, e.slots)
	if err != nil {
		return nil, err
	}
	defer release()
	language, ok := e.languageSpec(req.Language)
	if !ok {
		return nil, fmt.Errorf("unsupported programming language: %s", req.Language)
	}
	if len(req.Code) > maxSandboxSourceBytes || len(req.TestCases) == 0 || len(req.TestCases) > maxBatchTests {
		return nil, fmt.Errorf("coding execution requires 1–50 tests and source no larger than 32 KiB")
	}
	groups := map[int][]TestCase{}
	var caps []int
	for _, tc := range req.TestCases {
		if len(tc.Input) > maxSandboxInputBytes {
			return nil, fmt.Errorf("test input exceeds 16 KiB")
		}
		memory := configInt(req.RuntimeConfig, "memory_limit_mb", 256)
		if tc.MemoryLimitMB > 0 {
			memory = tc.MemoryLimitMB
		}
		if memory <= 0 || memory > e.cfg.MaxMemoryMB {
			memory = e.cfg.MaxMemoryMB
		}
		if _, exists := groups[memory]; !exists {
			caps = append(caps, memory)
		}
		groups[memory] = append(groups[memory], tc)
	}
	batches := []codingBatch{}
	for _, memory := range caps {
		batches = append(batches, e.splitCodingBatches(language, req, groups[memory], memory)...)
	}
	results := map[int64]TestResult{}
	for _, batchGroup := range batches {
		memory, tests := batchGroup.memory, batchGroup.tests
		script, budget := e.batchScript(language, req, tests)
		// Linux limits any one exec argument to 128 KiB, even with a larger ARG_MAX.
		if len(script) > 120*1024 {
			return nil, fmt.Errorf("test fixture batch exceeds the execution payload limit")
		}
		name := fmt.Sprintf("code-%x-%x", uint64(req.SubmissionID), time.Now().UnixNano())
		if err := e.createScriptJob(ctx, name, language, script, budget, memory); err != nil {
			return nil, fmt.Errorf("isolated executor could not start: %w", err)
		}
		batch, err := func() ([]TestResult, error) {
			// TTL cannot clean up an unfinished Job. Always delete on cancellation too.
			defer func() {
				cleanup, cancel := context.WithTimeout(context.Background(), 5*time.Second)
				defer cancel()
				e.deleteJob(cleanup, name)
			}()
			_, err := e.waitForJob(ctx, name, e.cfg.ProvisionTimeout+budget+10*time.Second)
			if err != nil {
				return nil, fmt.Errorf("executor unavailable: %w", err)
			}
			logs, reason, err := e.getJobLogs(ctx, name)
			if err != nil {
				return nil, err
			}
			if reason == "OOMKilled" {
				return parseOOMBatchOutput(logs, tests)
			}
			return parseBatchOutput(logs, tests)
		}()
		if err != nil {
			return nil, err
		}
		for _, tr := range batch {
			results[tr.TestCaseID] = tr
		}
	}
	result := &ExecutionResult{TotalTests: len(req.TestCases), MaxScore: 100, Status: "ACCEPTED"}
	totalWeight, passedWeight := 0, 0
	for _, tc := range req.TestCases {
		tr := results[tc.ID]
		if tr.Status == "OK" {
			tr.Status = "WRONG_ANSWER"
			if CompareOutput(tr.ActualOutput, tc.Expected) {
				tr.Status = "PASSED"
			}
		}
		weight := tc.Weight
		if weight <= 0 {
			weight = 1
		}
		totalWeight += weight
		if tr.Status == "PASSED" {
			result.PassedTests++
			passedWeight += weight
		} else if result.Status == "ACCEPTED" {
			result.Status = tr.Status
		}
		if tr.Status == "COMPILE_ERROR" {
			result.CompilerOutput = tr.ActualOutput
		}
		result.RuntimeMs += tr.RuntimeMs
		result.TestResults = append(result.TestResults, tr)
	}
	result.Score = float64(passedWeight) * 100 / float64(totalWeight)
	return result, nil
}

func shellQuote(value string) string { return "'" + strings.ReplaceAll(value, "'", "'\"'\"'") + "'" }

func (e *KubernetesCodingExecutor) batchScript(lang sandboxLanguage, req ExecutionRequest, tests []TestCase) (string, time.Duration) {
	var script strings.Builder
	fmt.Fprintf(&script, "set -eu\nmkdir -p /tmp/work\ncd /tmp/work\nprintf '%%s' '%s' | base64 -d > %s\n", base64.StdEncoding.EncodeToString([]byte(req.Code)), lang.sourceFile)
	// Bound disk growth, including malicious compiler diagnostics/program output.
	script.WriteString("compile_rc=0\nclock_ms() { awk '{printf \"%.0f\", $1 * 1000}' /proc/uptime; }\n")
	budget := time.Duration(0)
	if lang.compileCommand != "" {
		budget += e.cfg.MaxCompileTime + time.Second
		fmt.Fprintf(&script, "set +e\ntimeout -k 1s %s /bin/sh -c %s > compile.stdout 2> compile.stderr\ncompile_rc=$?\nset -e\n", timeoutSeconds(e.cfg.MaxCompileTime), shellQuote(lang.compileCommand))
	}
	for _, tc := range tests {
		limit := time.Duration(configInt(req.RuntimeConfig, "time_limit_ms", 2000)) * time.Millisecond
		if tc.TimeLimitMs > 0 {
			limit = time.Duration(tc.TimeLimitMs) * time.Millisecond
		}
		if limit <= 0 || limit > e.cfg.MaxTime {
			limit = e.cfg.MaxTime
		}
		budget += limit + 2*time.Second
		fmt.Fprintf(&script, `if [ "$compile_rc" -ne 0 ]; then
 status=COMPILE_ERROR
 head -c %d compile.stderr > diagnostic
 output=diagnostic
 elapsed=0
else
 printf '%%s' '%s' | base64 -d > input
 start=$(clock_ms)
 set +e
 timeout -k 1s %s /bin/sh -c %s < input > stdout 2> stderr
 rc=$?
 set -e
 elapsed=$(( $(clock_ms) - start ))
 status=OK
 output=stdout
 if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then status=TIME_LIMIT; output=stderr; elapsed=%d
 elif [ "$(wc -c < stdout)" -gt %d ] || [ "$(wc -c < stderr)" -gt %d ]; then status=RUNTIME_ERROR; printf 'Output limit exceeded' > stderr; output=stderr
 elif [ "$rc" -ne 0 ]; then status=RUNTIME_ERROR; output=stderr
 fi
fi
printf '__BDC_CASE__:%d:%%s:%%s:' "$status" "$elapsed"
head -c %d "$output" | base64 | tr -d '\n'
printf '\n'
`, maxCaseOutputBytes, base64.StdEncoding.EncodeToString([]byte(tc.Input)), timeoutSeconds(limit), shellQuote("ulimit -f 128; exec "+lang.runCommand), limit.Milliseconds(), maxCaseOutputBytes, maxCaseOutputBytes, tc.ID, maxCaseOutputBytes)
	}
	return script.String(), budget
}

func timeoutSeconds(d time.Duration) string {
	return strconv.FormatFloat(d.Seconds(), 'f', 3, 64) + "s"
}

func parseBatchOutput(logs string, tests []TestCase) ([]TestResult, error) {
	lines := strings.Split(strings.TrimSuffix(logs, "\n"), "\n")
	if len(lines) != len(tests) {
		return nil, fmt.Errorf("executor did not return all test results")
	}
	results := make([]TestResult, 0, len(tests))
	for i, line := range lines {
		fields := strings.SplitN(line, ":", 5)
		if len(fields) != 5 || fields[0] != "__BDC_CASE__" || fields[1] != strconv.FormatInt(tests[i].ID, 10) {
			return nil, fmt.Errorf("invalid executor result framing")
		}
		switch fields[2] {
		case "OK", "COMPILE_ERROR", "TIME_LIMIT", "RUNTIME_ERROR":
		default:
			return nil, fmt.Errorf("invalid executor result status")
		}
		ms, err := strconv.Atoi(fields[3])
		if err != nil || ms < 0 {
			return nil, fmt.Errorf("invalid executor runtime")
		}
		output, err := base64.StdEncoding.DecodeString(fields[4])
		if err != nil || len(output) > maxCaseOutputBytes {
			return nil, fmt.Errorf("invalid executor output")
		}
		results = append(results, TestResult{TestCaseID: tests[i].ID, Status: fields[2], ActualOutput: string(output), RuntimeMs: ms})
	}
	return results, nil
}

func acquireExecutionSlot(ctx context.Context, slots chan struct{}) (func(), error) {
	if slots == nil {
		return func() {}, nil
	}
	wait, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	select {
	case slots <- struct{}{}:
		return func() { <-slots }, nil
	case <-wait.Done():
		return nil, fmt.Errorf("executors are busy; please retry: %w", wait.Err())
	}
}

func parseOOMBatchOutput(logs string, tests []TestCase) ([]TestResult, error) {
	count := strings.Count(logs, "\n")
	if count >= len(tests) {
		return parseBatchOutput(logs, tests)
	}
	var results []TestResult
	if count > 0 {
		complete := strings.Join(strings.Split(logs, "\n")[:count], "\n") + "\n"
		var err error
		results, err = parseBatchOutput(complete, tests[:count])
		if err != nil {
			return nil, err
		}
	}
	for i := count; i < len(tests); i++ {
		status := "PENDING"
		if i == count {
			status = "MEMORY_LIMIT"
		}
		results = append(results, TestResult{TestCaseID: tests[i].ID, Status: status, ActualOutput: "Execution stopped after exceeding the memory limit."})
	}
	return results, nil
}

// Linux limits a single exec argument to 128 KiB. Split large input suites
// while retaining compile-once execution for each compatible payload batch.
type codingBatch struct {
	memory int
	tests  []TestCase
}

func (e *KubernetesCodingExecutor) splitCodingBatches(lang sandboxLanguage, req ExecutionRequest, tests []TestCase, memory int) []codingBatch {
	batches := []codingBatch{}
	for len(tests) > 0 {
		count := len(tests)
		for count > 1 {
			script, _ := e.batchScript(lang, req, tests[:count])
			if len(script) <= 120*1024 {
				break
			}
			count = (count + 1) / 2
		}
		batches = append(batches, codingBatch{memory: memory, tests: tests[:count]})
		tests = tests[count:]
	}
	return batches
}
