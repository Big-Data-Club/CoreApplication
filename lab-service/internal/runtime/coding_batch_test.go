package runtime

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os/exec"
	"strings"
	"testing"
	"time"

	"lab-service/internal/config"
)

func batchExecutor() *KubernetesCodingExecutor {
	return &KubernetesCodingExecutor{cfg: config.CodingSandboxConfig{Namespace: "lab-sandbox", PythonImage: "python:test", MaxTime: time.Second, MaxCompileTime: time.Second, ProvisionTimeout: 90 * time.Second, MaxMemoryMB: 512, MaxCPU: "1", PollInterval: time.Millisecond, JobTTLSeconds: 60}}
}

func TestCodingBatchOneJobAndInfrastructureDeadline(t *testing.T) {
	e := batchExecutor()
	creates, deletes := 0, 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodPost:
			creates++
			var job map[string]interface{}
			if err := json.NewDecoder(r.Body).Decode(&job); err != nil {
				t.Error(err)
			}
			spec := job["spec"].(map[string]interface{})
			if spec["activeDeadlineSeconds"].(float64) < 100 {
				t.Error("Job deadline did not include provisioning")
			}
			pod := spec["template"].(map[string]interface{})["spec"].(map[string]interface{})
			if pod["securityContext"].(map[string]interface{})["fsGroup"] != float64(1000) {
				t.Error("workspace is not writable by runner")
			}
			if pod["automountServiceAccountToken"] != false {
				t.Error("runner receives API token")
			}
			_, _ = w.Write([]byte(`{}`))
		case r.Method == http.MethodDelete:
			deletes++
			_, _ = w.Write([]byte(`{}`))
		case strings.Contains(r.URL.Path, "/log"):
			_, _ = w.Write([]byte("__BDC_CASE__:1:OK:10:" + base64.StdEncoding.EncodeToString([]byte("a\n")) + "\n__BDC_CASE__:2:OK:20:" + base64.StdEncoding.EncodeToString([]byte("b\n")) + "\n"))
		case strings.HasSuffix(r.URL.Path, "/pods"):
			_, _ = w.Write([]byte(`{"items":[{"metadata":{"name":"runner"}}]}`))
		default:
			_, _ = w.Write([]byte(`{"status":{"succeeded":1}}`))
		}
	}))
	defer server.Close()
	e.server, e.client = server.URL, server.Client()
	result, err := e.Execute(context.Background(), ExecutionRequest{Language: "python", Code: "print(input())", TestCases: []TestCase{{ID: 1, Expected: "a"}, {ID: 2, Expected: "b"}}})
	if err != nil {
		t.Fatal(err)
	}
	if creates != 1 || deletes != 1 || result.Status != "ACCEPTED" || result.Score != 100 || result.RuntimeMs != 30 {
		t.Fatalf("creates=%d deletes=%d result=%+v", creates, deletes, result)
	}
}

func TestBatchHarnessCompilesOnceAndFramesOutput(t *testing.T) {
	e := batchExecutor()
	dir := t.TempDir()
	language := sandboxLanguage{sourceFile: "solution.sh", compileCommand: "printf compiled >> /tmp/work/count && cp /tmp/work/solution.sh /tmp/work/solution", runCommand: "/bin/sh /tmp/work/solution"}
	tests := []TestCase{{ID: 1, Input: "hello"}, {ID: 2, Input: "world"}}
	script, _ := e.batchScript(language, ExecutionRequest{Code: "read value; printf '%s\\n__BDC_CASE__:999:OK:0:Zm9yZ2Vk\\n' \"$value\""}, tests)
	script = strings.ReplaceAll(script, "/tmp/work", dir)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	logs, err := exec.CommandContext(ctx, "/bin/sh", "-ec", script).CombinedOutput()
	if err != nil {
		t.Fatalf("%v: %s", err, logs)
	}
	results, err := parseBatchOutput(string(logs), tests)
	if err != nil {
		t.Fatalf("%v: %s", err, logs)
	}
	if len(results) != 2 || results[0].ActualOutput != "hello\n__BDC_CASE__:999:OK:0:Zm9yZ2Vk\n" {
		t.Fatalf("unexpected results %+v", results)
	}
	count, err := exec.Command("cat", dir+"/count").Output()
	if err != nil || string(count) != "compiled" {
		t.Fatalf("compiled more than once: %s %v", count, err)
	}
}

func TestBatchHarnessTimeoutsAndOutputLimit(t *testing.T) {
	for _, test := range []struct {
		name, code, status string
		compile            string
	}{
		{"timeout", "sleep 2", "TIME_LIMIT", ""},
		{"output", "head -c 20000 /dev/zero", "RUNTIME_ERROR", ""},
		{"compile timeout", "echo ok", "COMPILE_ERROR", "sleep 2"},
	} {
		t.Run(test.name, func(t *testing.T) {
			e := batchExecutor()
			e.cfg.MaxCompileTime = 50 * time.Millisecond
			tests := []TestCase{{ID: 1, TimeLimitMs: 50}}
			script, _ := e.batchScript(sandboxLanguage{sourceFile: "solution.sh", runCommand: "/bin/sh /tmp/work/solution.sh", compileCommand: test.compile}, ExecutionRequest{Code: test.code}, tests)
			script = strings.ReplaceAll(script, "/tmp/work", t.TempDir())
			ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			defer cancel()
			logs, err := exec.CommandContext(ctx, "/bin/sh", "-ec", script).CombinedOutput()
			if err != nil {
				t.Fatalf("%v: %s", err, logs)
			}
			results, err := parseBatchOutput(string(logs), tests)
			if err != nil || results[0].Status != test.status {
				t.Fatalf("results=%+v err=%v logs=%s", results, err, logs)
			}
		})
	}
}

func TestBatchRejectsMissingAndForgedResults(t *testing.T) {
	tests := []TestCase{{ID: 1}, {ID: 2}}
	for _, logs := range []string{"", "__BDC_CASE__:1:OK:0:\n", "__BDC_CASE__:1:OK:0:\n__BDC_CASE__:3:OK:0:\n", "__BDC_CASE__:1:OK:0:invalid!\n__BDC_CASE__:2:OK:0:\n"} {
		if _, err := parseBatchOutput(logs, tests); err == nil {
			t.Fatalf("accepted invalid results %q", logs)
		}
	}
	if durationSeconds(1500*time.Millisecond) != 2 {
		t.Fatal("deadline rounded down")
	}
}

func TestOOMRetainsCompletedTestsAndStopsRemaining(t *testing.T) {
	tests := []TestCase{{ID: 1}, {ID: 2}, {ID: 3}}
	results, err := parseOOMBatchOutput("__BDC_CASE__:1:OK:10:YQ==\n", tests)
	if err != nil || len(results) != 3 || results[0].Status != "OK" || results[1].Status != "MEMORY_LIMIT" || results[2].Status != "PENDING" {
		t.Fatalf("results=%+v err=%v", results, err)
	}
}

func TestAdmissionCancellationDoesNotLeakCapacity(t *testing.T) {
	slots := make(chan struct{}, 1)
	release, err := acquireExecutionSlot(context.Background(), slots)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := acquireExecutionSlot(ctx, slots); err == nil {
		t.Fatal("cancelled waiter acquired a slot")
	}
	release()
	release, err = acquireExecutionSlot(context.Background(), slots)
	if err != nil {
		t.Fatal(err)
	}
	release()
	if len(slots) != 0 {
		t.Fatal("executor slot leaked")
	}
}

func TestLargeCodingFixturesSplitIntoExecutablePayloads(t *testing.T) {
	e := batchExecutor()
	lang, _ := e.languageSpec("python")
	req := ExecutionRequest{Language: "python", Code: strings.Repeat("#", 32768)}
	for i := 0; i < 50; i++ {
		req.TestCases = append(req.TestCases, TestCase{ID: int64(i + 1), Input: strings.Repeat("x", 16384)})
	}
	groups := e.splitCodingBatches(lang, req, req.TestCases, 256)
	if len(groups) <= 1 {
		t.Fatal("oversized fixture suite was not split")
	}
	total := 0
	for _, g := range groups {
		script, _ := e.batchScript(lang, req, g.tests)
		if len(script) > 120*1024 {
			t.Fatal("oversized exec argument")
		}
		total += len(g.tests)
	}
	if total != 50 {
		t.Fatalf("lost cases: %d", total)
	}
}
