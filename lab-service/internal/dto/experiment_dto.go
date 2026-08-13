package dto

import "time"

// CreateLabVersionRequest is the immutable authoring snapshot stored for one lab version.
type CreateLabVersionRequest struct {
	Definition ExperimentDefinitionRequest `json:"definition" binding:"required"`
}

type ExperimentDefinitionRequest struct {
	Domain               string                      `json:"domain" binding:"required"`
	InquiryLevel         string                      `json:"inquiry_level" binding:"required"`
	WorkflowSchemaVersion int                         `json:"workflow_schema_version"`
	ModelVersion         string                      `json:"model_version" binding:"required,max=100"`
	LearningObjectives   []string                    `json:"learning_objectives"`
	Config               map[string]interface{}      `json:"config"`
	Nodes                []WorkflowNodeRequest       `json:"nodes"`
	Edges                []WorkflowEdgeRequest       `json:"edges"`
	Variables            []ExperimentVariableRequest `json:"variables"`
}

type WorkflowNodeRequest struct {
	Key              string                 `json:"key" binding:"required,max=100"`
	Type             string                 `json:"type" binding:"required,max=40"`
	Title            string                 `json:"title" binding:"required,max=255"`
	Config           map[string]interface{} `json:"config"`
	RequiredEvidence []string               `json:"required_evidence"`
	OrderHint        int                    `json:"order_hint"`
}

type WorkflowEdgeRequest struct {
	From                string `json:"from" binding:"required,max=100"`
	To                  string `json:"to" binding:"required,max=100"`
	ConditionExpression string `json:"condition_expression" binding:"max=2000"`
	Priority            int    `json:"priority"`
}

type ExperimentVariableRequest struct {
	Key          string      `json:"key" binding:"required,max=100"`
	DisplayName  string      `json:"display_name" binding:"required,max=255"`
	Role         string      `json:"role" binding:"required"`
	DataType     string      `json:"data_type" binding:"required"`
	Unit         string      `json:"unit" binding:"max=50"`
	MinValue     *float64    `json:"min_value"`
	MaxValue     *float64    `json:"max_value"`
	DefaultValue interface{} `json:"default_value"`
	SourceID     string      `json:"source_id" binding:"max=255"`
}

type LabVersionResponse struct {
	ID                 int64                       `json:"id"`
	LabID              int64                       `json:"lab_id"`
	VersionNumber      int                         `json:"version_number"`
	Status             string                      `json:"status"`
	DefinitionHash     string                      `json:"definition_hash"`
	Definition         ExperimentDefinitionRequest `json:"definition"`
	CreatedBy          int64                       `json:"created_by"`
	ValidatedAt        *time.Time                  `json:"validated_at,omitempty"`
	PublishedAt        *time.Time                  `json:"published_at,omitempty"`
	CreatedAt          time.Time                   `json:"created_at"`
	UpdatedAt          time.Time                   `json:"updated_at"`
}

type ValidationIssue struct {
	Severity string `json:"severity"`
	Code     string `json:"code"`
	Path     string `json:"path"`
	Message  string `json:"message"`
}

type LabVersionValidationResponse struct {
	Valid  bool              `json:"valid"`
	Issues []ValidationIssue `json:"issues"`
}

type CreateRunRequest struct {
	IdempotencyKey string `json:"idempotency_key" binding:"required,min=8,max=128"`
}

type RunResponse struct {
	ID               int64      `json:"id"`
	LabID            int64      `json:"lab_id"`
	LabVersionID     int64      `json:"lab_version_id"`
	LabVersionNumber int        `json:"lab_version_number"`
	UserID           int64      `json:"user_id"`
	Status           string     `json:"status"`
	CurrentNodeKey   *string    `json:"current_node_key,omitempty"`
	LastEventSeq     int64      `json:"last_event_seq"`
	StartedAt        time.Time  `json:"started_at"`
	EndedAt          *time.Time `json:"ended_at,omitempty"`
	UpdatedAt        time.Time  `json:"updated_at"`
}

type RunSummaryResponse struct {
	RunResponse
	LearnerName  string `json:"learner_name"`
	LearnerEmail string `json:"learner_email"`
	TrialCount   int    `json:"trial_count"`
}

type CreateTrialRequest struct {
	Seed           *int64                 `json:"seed" binding:"omitempty,min=0"`
	ConfigSnapshot map[string]interface{} `json:"config_snapshot"`
}

type TrialResponse struct {
	ID             int64                  `json:"id"`
	RunID          int64                  `json:"run_id"`
	TrialNumber    int                    `json:"trial_number"`
	Seed           int64                  `json:"seed"`
	ModelVersion   string                 `json:"model_version"`
	ConfigSnapshot map[string]interface{} `json:"config_snapshot"`
	Status         string                 `json:"status"`
	StartedAt      *time.Time             `json:"started_at,omitempty"`
	EndedAt        *time.Time             `json:"ended_at,omitempty"`
	CreatedAt      time.Time              `json:"created_at"`
}

type EvidenceObject struct {
	Type string `json:"type" binding:"required,max=60"`
	ID   string `json:"id" binding:"required,max=255"`
}

type AppendEvidenceRequest struct {
	ClientEventID string                 `json:"client_event_id" binding:"required,uuid"`
	TrialID       *int64                 `json:"trial_id" binding:"omitempty,min=1"`
	WorkflowNodeKey string               `json:"workflow_node_key" binding:"omitempty,max=100"`
	Verb          string                 `json:"verb" binding:"required,max=60"`
	Object        EvidenceObject         `json:"object" binding:"required"`
	Result        map[string]interface{} `json:"result"`
	Context       map[string]interface{} `json:"context"`
	SimTimeMs     *int64                 `json:"sim_time_ms" binding:"omitempty,min=0"`
}

type EvidenceEventResponse struct {
	EventID       string                 `json:"event_id"`
	ClientEventID string                 `json:"client_event_id"`
	SchemaVersion int                    `json:"schema_version"`
	RunID         int64                  `json:"run_id"`
	TrialID       *int64                 `json:"trial_id,omitempty"`
	SeqNo         int64                  `json:"seq_no"`
	ActorID       int64                  `json:"actor_id"`
	ActorType     string                 `json:"actor_type"`
	Verb          string                 `json:"verb"`
	Object        EvidenceObject         `json:"object"`
	Result        map[string]interface{} `json:"result"`
	Context       map[string]interface{} `json:"context"`
	SimTimeMs     *int64                 `json:"sim_time_ms,omitempty"`
	OccurredAt    time.Time              `json:"occurred_at"`
	IngestedAt    time.Time              `json:"ingested_at"`
}
