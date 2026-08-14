package runtime

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
	"time"

	"lab-service/internal/config"
)

// HPCRunner submits an already constrained job to one operator-provisioned
// Slurm login node. The browser never supplies an SSH host, SSH user, key,
// known_hosts file, or a remote command.
type HPCRunner struct{ cfg config.SLURMConfig }

func NewHPCRunner(cfg config.SLURMConfig) *HPCRunner { return &HPCRunner{cfg: cfg} }

func (r *HPCRunner) Type() RuntimeType { return RuntimeHPC }

func (r *HPCRunner) Validate(labConfig map[string]interface{}) error {
	if !r.cfg.Enabled {
		return fmt.Errorf("HPC scheduler profile is not enabled")
	}
	if strings.TrimSpace(r.cfg.ProfileID) == "" {
		return fmt.Errorf("HPC scheduler profile is missing an ID")
	}
	profileID, _ := labConfig["hpc_profile_id"].(string)
	if profileID != r.cfg.ProfileID {
		return fmt.Errorf("lab must select the configured HPC scheduler profile")
	}
	if r.cfg.Transport != "SSH" {
		return fmt.Errorf("unsupported HPC transport %q", r.cfg.Transport)
	}
	if !safeHost(r.cfg.SSHHost) || !safeIdentifier(r.cfg.SSHUser) || r.cfg.SSHPort < 1 || r.cfg.SSHPort > 65535 {
		return fmt.Errorf("HPC SSH profile is incomplete or invalid")
	}
	if !regularFile(r.cfg.SSHIdentityFile) || !regularFile(r.cfg.SSHKnownHostsFile) {
		return fmt.Errorf("HPC SSH credentials or pinned host keys are not mounted")
	}
	if !allowed(r.cfg.DefaultPartition, r.cfg.AllowedPartitions) || !allowed(r.cfg.DefaultAccount, r.cfg.AllowedAccounts) || !allowed(r.cfg.DefaultQOS, r.cfg.AllowedQOS) {
		return fmt.Errorf("HPC profile defaults are outside its allowlists")
	}
	return nil
}

func (r *HPCRunner) Execute(ctx context.Context, req ExecutionRequest) (*ExecutionResult, error) {
	if err := r.Validate(req.RuntimeConfig); err != nil {
		return nil, err
	}
	if len(req.Script) == 0 || len(req.Script) > 64*1024 || strings.ContainsRune(req.Script, '\x00') {
		return nil, fmt.Errorf("job script must be between 1 and 65536 bytes")
	}

	limits, err := r.resolveLimits(req.RuntimeConfig)
	if err != nil {
		return nil, err
	}
	requested, err := r.requestedResources(req.Resources, limits)
	if err != nil {
		return nil, err
	}

	jobName := fmt.Sprintf("lab-%d-submission-%d", req.LabID, req.SubmissionID)
	args := []string{
		"-o", "BatchMode=yes",
		"-o", "IdentitiesOnly=yes",
		"-o", "StrictHostKeyChecking=yes",
		"-o", "UserKnownHostsFile=" + r.cfg.SSHKnownHostsFile,
		"-i", r.cfg.SSHIdentityFile,
		"-p", strconv.Itoa(r.cfg.SSHPort),
		r.cfg.SSHUser + "@" + r.cfg.SSHHost,
		"sbatch", "--parsable",
		"--job-name=" + jobName,
		"--partition=" + limits.partition,
		"--account=" + limits.account,
		"--qos=" + limits.qos,
		"--time=" + requested.maxTime,
		"--nodes=" + strconv.Itoa(requested.nodes),
		"--ntasks=" + strconv.Itoa(requested.tasks),
		"--cpus-per-task=" + strconv.Itoa(requested.cpusPerTask),
		"--mem=" + strconv.Itoa(requested.memoryMB),
		"--export=NONE",
	}
	if requested.gpuCount > 0 {
		args = append(args, "--gres=gpu:"+strconv.Itoa(requested.gpuCount))
	}

	// Command-line flags are intentionally appended by the service, so learner
	// #SBATCH lines cannot raise a lab's allocation. Slurm account/QOS policy
	// must additionally prohibit nested submissions for the service account.
	commandCtx, cancel := context.WithTimeout(ctx, r.cfg.CommandTimeout)
	defer cancel()
	cmd := exec.CommandContext(commandCtx, "ssh", args...)
	cmd.Stdin = strings.NewReader(stripSBATCHDirectives(req.Script))
	output, err := cmd.CombinedOutput()
	if err != nil {
		return nil, fmt.Errorf("Slurm submission failed: %s", boundedOutput(output))
	}
	jobID := parseJobID(string(output))
	if jobID == "" {
		return nil, fmt.Errorf("Slurm did not return a job ID")
	}
	return &ExecutionResult{Status: "PENDING", JobID: jobID, Stdout: strings.TrimSpace(string(output))}, nil
}

type hpcLimits struct {
	partition, account, qos, maxTime string
	maxNodes, maxTasks, maxCPUsPerTask, maxMemoryMB, maxGPUCount int
}

type hpcRequest struct {
	nodes, tasks, cpusPerTask, memoryMB, gpuCount int
	maxTime string
}

func (r *HPCRunner) resolveLimits(lab map[string]interface{}) (hpcLimits, error) {
	limits := hpcLimits{
		partition: r.cfg.DefaultPartition, account: r.cfg.DefaultAccount, qos: r.cfg.DefaultQOS,
		maxTime: r.cfg.MaxTime, maxNodes: r.cfg.MaxNodes, maxTasks: r.cfg.MaxTasks,
		maxCPUsPerTask: r.cfg.MaxCPUsPerTask, maxMemoryMB: r.cfg.MaxMemoryMB, maxGPUCount: r.cfg.MaxGPUCount,
	}
	// A lab may narrow limits, never widen the platform profile.
	if value, ok := lab["slurm_partition"].(string); ok && value != "" { limits.partition = value }
	if value, ok := lab["slurm_account"].(string); ok && value != "" { limits.account = value }
	if value, ok := lab["slurm_qos"].(string); ok && value != "" { limits.qos = value }
	if value, ok := lab["slurm_max_time"].(string); ok && value != "" { limits.maxTime = value }
	limits.maxNodes = narrowedInt(lab, "max_nodes", limits.maxNodes)
	limits.maxTasks = narrowedInt(lab, "max_tasks", limits.maxTasks)
	limits.maxCPUsPerTask = narrowedInt(lab, "max_cpus_per_task", limits.maxCPUsPerTask)
	limits.maxMemoryMB = narrowedInt(lab, "max_memory_mb", limits.maxMemoryMB)
	limits.maxGPUCount = narrowedInt(lab, "max_gpu_count", limits.maxGPUCount)
	if !allowed(limits.partition, r.cfg.AllowedPartitions) || !allowed(limits.account, r.cfg.AllowedAccounts) || !allowed(limits.qos, r.cfg.AllowedQOS) ||
		!safeIdentifier(limits.partition) || !safeIdentifier(limits.account) || !safeIdentifier(limits.qos) ||
		limits.maxNodes < 1 || limits.maxTasks < 1 || limits.maxCPUsPerTask < 1 || limits.maxMemoryMB < 64 || limits.maxGPUCount < 0 ||
		!validSlurmTime(limits.maxTime) || durationExceeds(limits.maxTime, r.cfg.MaxTime) {
		return hpcLimits{}, fmt.Errorf("lab HPC limits are invalid or exceed the scheduler profile")
	}
	return limits, nil
}

func (r *HPCRunner) requestedResources(raw map[string]interface{}, limits hpcLimits) (hpcRequest, error) {
	request := hpcRequest{nodes: 1, tasks: 1, cpusPerTask: 1, memoryMB: 512, gpuCount: 0, maxTime: limits.maxTime}
	request.nodes = requestInt(raw, "num_nodes", request.nodes)
	request.tasks = requestInt(raw, "num_tasks", request.tasks)
	request.cpusPerTask = requestInt(raw, "cpus_per_task", request.cpusPerTask)
	request.memoryMB = requestInt(raw, "memory_mb", request.memoryMB)
	request.gpuCount = requestInt(raw, "gpu_count", request.gpuCount)
	if value, ok := raw["max_time"].(string); ok && value != "" { request.maxTime = value }
	if request.nodes < 1 || request.nodes > limits.maxNodes || request.tasks < 1 || request.tasks > limits.maxTasks ||
		request.cpusPerTask < 1 || request.cpusPerTask > limits.maxCPUsPerTask || request.memoryMB < 64 || request.memoryMB > limits.maxMemoryMB ||
		request.gpuCount < 0 || request.gpuCount > limits.maxGPUCount || !validSlurmTime(request.maxTime) || durationExceeds(request.maxTime, limits.maxTime) {
		return hpcRequest{}, fmt.Errorf("requested HPC resources exceed this lab's limits")
	}
	return request, nil
}

func allowed(value string, allowlist []string) bool {
	if value == "" || len(allowlist) == 0 { return false }
	for _, allowedValue := range allowlist { if value == strings.TrimSpace(allowedValue) { return true } }
	return false
}

func narrowedInt(values map[string]interface{}, key string, max int) int {
	value := requestInt(values, key, max)
	if value <= 0 || value > max { return -1 }
	return value
}

func requestInt(values map[string]interface{}, key string, fallback int) int {
	switch value := values[key].(type) {
	case int: return value
	case int64: return int(value)
	case float64: return int(value)
	case jsonNumber: parsed, err := strconv.Atoi(string(value)); if err == nil { return parsed }
	}
	return fallback
}

// jsonNumber avoids importing a JSON decoder only to support values created by callers.
type jsonNumber string

var identifierPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$`)
var hostPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$`)
var jobIDPattern = regexp.MustCompile(`^([0-9]+)(?:;[^[:space:]]+)?\s*$`)
var slurmTimePattern = regexp.MustCompile(`^(?:[0-9]+-)?[0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?$`)

func safeIdentifier(value string) bool { return identifierPattern.MatchString(value) }
func safeHost(value string) bool { return hostPattern.MatchString(value) && !strings.Contains(value, "..") }
func regularFile(path string) bool { info, err := os.Stat(path); return err == nil && info.Mode().IsRegular() }
func validSlurmTime(value string) bool { return slurmTimePattern.MatchString(value) }

func durationExceeds(value, maximum string) bool {
	requested, reqOK := slurmDuration(value)
	max, maxOK := slurmDuration(maximum)
	return !reqOK || !maxOK || requested > max
}

func slurmDuration(value string) (time.Duration, bool) {
	if !validSlurmTime(value) { return 0, false }
	days := 0
	parts := strings.Split(value, "-")
	clock := parts[len(parts)-1]
	if len(parts) == 2 { parsed, err := strconv.Atoi(parts[0]); if err != nil { return 0, false }; days = parsed }
	segments := strings.Split(clock, ":")
	hours, _ := strconv.Atoi(segments[0]); minutes, _ := strconv.Atoi(segments[1]); seconds := 0
	if len(segments) == 3 { seconds, _ = strconv.Atoi(segments[2]) }
	if minutes > 59 || seconds > 59 { return 0, false }
	return time.Duration(days)*24*time.Hour + time.Duration(hours)*time.Hour + time.Duration(minutes)*time.Minute + time.Duration(seconds)*time.Second, true
}

func stripSBATCHDirectives(script string) string {
	lines := strings.Split(script, "\n")
	kept := lines[:0]
	for _, line := range lines { if !strings.HasPrefix(strings.TrimSpace(line), "#SBATCH") { kept = append(kept, line) } }
	return strings.Join(kept, "\n")
}

func parseJobID(output string) string { match := jobIDPattern.FindStringSubmatch(strings.TrimSpace(output)); if len(match) == 2 { return match[1] }; return "" }
func boundedOutput(output []byte) string { value := strings.TrimSpace(string(output)); if len(value) > 1024 { return value[:1024] }; return value }
