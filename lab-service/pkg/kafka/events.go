package kafka

// ── Topic constants ─────────────────────────────────────────────
const (
	TopicJobCommand       = "lab.job.command"
	TopicJobStatus        = "lab.job.status"
	TopicSessionIdle      = "lab.session.idle"
	TopicSessionCheckpoint = "lab.session.checkpoint"
)

// ── Event types ─────────────────────────────────────────────────

// JobCommandEvent is published by lab-service, consumed by lab-worker.
type JobCommandEvent struct {
	JobID         string                 `json:"job_id"`
	SubmissionID  int64                  `json:"submission_id"`
	SessionID     int64                  `json:"session_id,omitempty"`
	UserID        int64                  `json:"user_id"`
	LabID         int64                  `json:"lab_id"`
	CommandType   string                 `json:"command_type"` // SUBMIT_JOB, CANCEL_JOB
	ScriptContent string                 `json:"script_content,omitempty"`
	Resources     map[string]interface{} `json:"resources,omitempty"`
}

// JobStatusEvent is published by lab-worker, consumed by lab-service.
type JobStatusEvent struct {
	JobID        string `json:"job_id"`
	SubmissionID int64  `json:"submission_id"`
	Status       string `json:"status"`
	SlurmJobID   int64  `json:"slurm_job_id,omitempty"`
	ExitCode     int    `json:"exit_code,omitempty"`
	StdoutKey    string `json:"stdout_key,omitempty"`
	StderrKey    string `json:"stderr_key,omitempty"`
	Error        string `json:"error,omitempty"`
}

// SessionIdleEvent is published by lab-proxy when a session is idle.
type SessionIdleEvent struct {
	SessionID int64  `json:"session_id"`
	IdleSince string `json:"idle_since"`
}
