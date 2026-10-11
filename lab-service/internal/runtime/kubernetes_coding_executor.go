package runtime

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"lab-service/internal/config"
)

const serviceAccountTokenPath = "/var/run/secrets/kubernetes.io/serviceaccount/token"
const serviceAccountCAPath = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

const maxSandboxSourceBytes = 32 * 1024
const maxSandboxInputBytes = 16 * 1024

// KubernetesCodingExecutor is a deliberately small controller client. It may
// create/read/delete Jobs and read Pod logs only; RBAC grants no secret, exec,
// service or namespace access. Each submission gets a network-isolated pod; test processes are fresh.
type KubernetesCodingExecutor struct {
	slots  chan struct{}
	cfg    config.CodingSandboxConfig
	client *http.Client
	token  string
	server string
}

type sandboxLanguage struct {
	image          string
	sourceFile     string
	compileCommand string
	runCommand     string
}

func NewKubernetesCodingExecutor(cfg config.CodingSandboxConfig) (*KubernetesCodingExecutor, error) {
	if !cfg.Enabled {
		return nil, nil
	}
	if cfg.MaxConcurrentJobs <= 0 || cfg.MaxConcurrentJobs > 16 {
		cfg.MaxConcurrentJobs = 4
	}
	if cfg.MaxTime <= 0 {
		cfg.MaxTime = 10 * time.Second
	}
	if cfg.MaxCompileTime <= 0 {
		cfg.MaxCompileTime = 30 * time.Second
	}
	if cfg.ProvisionTimeout <= 0 {
		cfg.ProvisionTimeout = 90 * time.Second
	}
	if cfg.MaxMemoryMB <= 0 {
		cfg.MaxMemoryMB = 512
	}
	if cfg.MaxCPU == "" {
		cfg.MaxCPU = "1"
	}
	if cfg.PollInterval <= 0 {
		cfg.PollInterval = 250 * time.Millisecond
	}
	if cfg.JobTTLSeconds <= 0 {
		cfg.JobTTLSeconds = 60
	}

	token, err := os.ReadFile(serviceAccountTokenPath)
	if err != nil || strings.TrimSpace(string(token)) == "" {
		return nil, fmt.Errorf("coding sandbox service-account token is unavailable")
	}
	caBytes, err := os.ReadFile(serviceAccountCAPath)
	if err != nil {
		return nil, fmt.Errorf("coding sandbox cluster CA is unavailable: %w", err)
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(caBytes) {
		return nil, fmt.Errorf("coding sandbox cluster CA is invalid")
	}

	requestTimeout := cfg.ProvisionTimeout + cfg.MaxCompileTime + cfg.MaxTime + 30*time.Second
	return &KubernetesCodingExecutor{
		cfg:    cfg,
		slots:  make(chan struct{}, cfg.MaxConcurrentJobs),
		token:  strings.TrimSpace(string(token)),
		server: "https://kubernetes.default.svc",
		client: &http.Client{
			Timeout: requestTimeout,
			Transport: &http.Transport{
				TLSClientConfig: &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12},
			},
		},
	}, nil
}

func (e *KubernetesCodingExecutor) languageSpec(value string) (sandboxLanguage, bool) {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "python", "python3":
		return sandboxLanguage{image: e.cfg.PythonImage, sourceFile: "solution.py", runCommand: "python3 -I /tmp/work/solution.py"}, true
	case "c":
		return sandboxLanguage{image: e.cfg.CImage, sourceFile: "solution.c", compileCommand: "gcc -O2 -pipe /tmp/work/solution.c -o /tmp/work/solution", runCommand: "/tmp/work/solution"}, true
	case "cpp", "c++":
		return sandboxLanguage{image: e.cfg.CPPImage, sourceFile: "solution.cpp", compileCommand: "g++ -O2 -pipe /tmp/work/solution.cpp -o /tmp/work/solution", runCommand: "/tmp/work/solution"}, true
	case "java":
		return sandboxLanguage{image: e.cfg.JavaImage, sourceFile: "Main.java", compileCommand: "mkdir -p /tmp/work/classes && javac -J-Xmx128m -d /tmp/work/classes /tmp/work/Main.java", runCommand: "java -XX:MaxRAMPercentage=60 -XX:ReservedCodeCacheSize=32m -Xss512k -cp /tmp/work/classes Main"}, true
	case "go", "golang":
		return sandboxLanguage{image: e.cfg.GoImage, sourceFile: "main.go", compileCommand: "GOCACHE=/tmp/work/go-cache GO111MODULE=off go build -trimpath -o /tmp/work/solution /tmp/work/main.go", runCommand: "/tmp/work/solution"}, true
	case "rust", "rs":
		return sandboxLanguage{image: e.cfg.RustImage, sourceFile: "main.rs", compileCommand: "rustc -O -o /tmp/work/solution /tmp/work/main.rs", runCommand: "/tmp/work/solution"}, true
	case "scala":
		return sandboxLanguage{image: e.cfg.ScalaImage, sourceFile: "Main.scala", compileCommand: "mkdir -p /tmp/work/classes && scalac -d /tmp/work/classes /tmp/work/Main.scala", runCommand: "scala -cp /tmp/work/classes Main"}, true
	default:
		return sandboxLanguage{}, false
	}
}

func (e *KubernetesCodingExecutor) createScriptJob(ctx context.Context, name string, language sandboxLanguage, script string, executionBudget time.Duration, memoryMB int) error {
	// A Job deadline includes scheduling and image pulls, not just user CPU time.
	activeDeadline := durationSeconds(e.cfg.ProvisionTimeout + executionBudget + 10*time.Second)
	requestMemory := 128
	if memoryMB < requestMemory {
		requestMemory = memoryMB
	}
	podSpec := map[string]interface{}{
		"serviceAccountName":            "lab-sandbox-runner",
		"automountServiceAccountToken":  false,
		"restartPolicy":                 "Never",
		"terminationGracePeriodSeconds": 1,
		"securityContext": map[string]interface{}{
			"runAsNonRoot": true,
			"runAsUser":    1000,
			"runAsGroup":   1000,
			"fsGroup":      1000,
			"seccompProfile": map[string]interface{}{
				"type": "RuntimeDefault",
			},
		},
		"containers": []interface{}{map[string]interface{}{
			"name":            "runner",
			"image":           language.image,
			"imagePullPolicy": "IfNotPresent",
			"command":         []string{"/bin/sh", "-ec", script},
			"env": []interface{}{
				map[string]interface{}{"name": "HOME", "value": "/tmp/work"},
				map[string]interface{}{"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
			},
			"resources": map[string]interface{}{
				"requests": map[string]string{"cpu": "100m", "memory": strconv.Itoa(requestMemory) + "Mi", "ephemeral-storage": "64Mi"},
				"limits":   map[string]string{"cpu": e.cfg.MaxCPU, "memory": strconv.Itoa(memoryMB) + "Mi", "ephemeral-storage": "512Mi"},
			},
			"securityContext": map[string]interface{}{
				"allowPrivilegeEscalation": false,
				"readOnlyRootFilesystem":   true,
				"capabilities":             map[string]interface{}{"drop": []string{"ALL"}},
			},
			"volumeMounts": []interface{}{map[string]interface{}{"name": "tmp", "mountPath": "/tmp"}},
		}},
		"volumes": []interface{}{map[string]interface{}{"name": "tmp", "emptyDir": map[string]interface{}{"sizeLimit": "512Mi"}}},
	}
	job := map[string]interface{}{
		"apiVersion": "batch/v1",
		"kind":       "Job",
		"metadata": map[string]interface{}{
			"name": name,
			"labels": map[string]string{
				"app.kubernetes.io/name":       "lab-code-run",
				"app.kubernetes.io/managed-by": "lab-service",
			},
		},
		"spec": map[string]interface{}{
			"backoffLimit":            0,
			"activeDeadlineSeconds":   activeDeadline,
			"ttlSecondsAfterFinished": e.cfg.JobTTLSeconds,
			"template": map[string]interface{}{
				"metadata": map[string]interface{}{
					"labels": map[string]string{
						"job-name":               name,
						"app.kubernetes.io/name": "lab-code-run",
					},
				},
				"spec": podSpec,
			},
		},
	}
	return e.requestJSON(ctx, http.MethodPost, "/apis/batch/v1/namespaces/"+e.cfg.Namespace+"/jobs", job, nil)
}

func (e *KubernetesCodingExecutor) waitForJob(ctx context.Context, name string, timeout time.Duration) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	deadline := time.NewTimer(timeout)
	defer deadline.Stop()
	ticker := time.NewTicker(e.cfg.PollInterval)
	defer ticker.Stop()
	for {
		var job struct {
			Status struct {
				Succeeded int `json:"succeeded"`
				Failed    int `json:"failed"`
			} `json:"status"`
		}
		if err := e.requestJSON(ctx, http.MethodGet, "/apis/batch/v1/namespaces/"+e.cfg.Namespace+"/jobs/"+name, nil, &job); err != nil {
			return "", err
		}
		if job.Status.Succeeded > 0 {
			return "SUCCEEDED", nil
		}
		if job.Status.Failed > 0 {
			return "FAILED", nil
		}
		select {
		case <-ctx.Done():
			return "", ctx.Err()
		case <-deadline.C:
			return "", fmt.Errorf("sandbox exceeded its orchestration deadline")
		case <-ticker.C:
		}
	}
}

func (e *KubernetesCodingExecutor) getJobLogs(ctx context.Context, jobName string) (string, string, error) {
	var pods struct {
		Items []struct {
			Metadata struct {
				Name string `json:"name"`
			} `json:"metadata"`
			Status struct {
				ContainerStatuses []struct {
					State struct {
						Terminated *struct {
							Reason string `json:"reason"`
						} `json:"terminated"`
					} `json:"state"`
				} `json:"containerStatuses"`
			} `json:"status"`
		} `json:"items"`
	}
	path := "/api/v1/namespaces/" + e.cfg.Namespace + "/pods?labelSelector=" + url.QueryEscape("job-name="+jobName)
	if err := e.requestJSON(ctx, http.MethodGet, path, nil, &pods); err != nil {
		return "", "", err
	}
	if len(pods.Items) == 0 {
		return "", "", fmt.Errorf("sandbox pod was not found")
	}
	reason := ""
	for _, status := range pods.Items[0].Status.ContainerStatuses {
		if status.State.Terminated != nil {
			reason = status.State.Terminated.Reason
		}
	}
	logs, err := e.requestText(ctx, "/api/v1/namespaces/"+e.cfg.Namespace+"/pods/"+pods.Items[0].Metadata.Name+"/log?container=runner")
	return logs, reason, err
}

func (e *KubernetesCodingExecutor) deleteJob(ctx context.Context, name string) {
	_ = e.requestJSON(ctx, http.MethodDelete, "/apis/batch/v1/namespaces/"+e.cfg.Namespace+"/jobs/"+name, nil, nil)
}

func (e *KubernetesCodingExecutor) requestJSON(ctx context.Context, method, path string, body interface{}, output interface{}) error {
	var reader io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(encoded)
	}
	req, err := http.NewRequestWithContext(ctx, method, e.server+path, reader)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+e.token)
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := e.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(io.LimitReader(resp.Body, 128*1024))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("Kubernetes API %s: %s", resp.Status, strings.TrimSpace(string(data)))
	}
	if output != nil && len(data) > 0 {
		return json.Unmarshal(data, output)
	}
	return nil
}

func (e *KubernetesCodingExecutor) requestText(ctx context.Context, path string) (string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, e.server+path, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Authorization", "Bearer "+e.token)
	resp, err := e.client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(io.LimitReader(resp.Body, maxBatchLogBytes+1))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("Kubernetes API %s: %s", resp.Status, strings.TrimSpace(string(data)))
	}
	if len(data) > maxBatchLogBytes {
		return "", fmt.Errorf("sandbox output exceeds limit")
	}
	return string(data), nil
}

func durationSeconds(value time.Duration) int {
	seconds := int((value + time.Second - 1) / time.Second)
	if seconds < 1 {
		return 1
	}
	return seconds
}
