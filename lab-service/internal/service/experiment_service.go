package service

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math/big"
	"net/http"
	"regexp"
	"strings"

	"lab-service/internal/dto"
	"lab-service/internal/repository"
)

const maxEvidencePayloadBytes = 64 * 1024

var identifierPattern = regexp.MustCompile(`^[a-z][a-z0-9_-]{0,99}$`)

var allowedNodeTypes = map[string]bool{
	"INSTRUCTION": true, "QUESTION": true, "PREDICTION": true,
	"CONFIGURE": true, "BUILD": true, "RUN": true, "MEASURE": true,
	"CHECKPOINT": true, "ANALYZE": true, "EXPLAIN": true,
	"ITERATE": true, "REFLECT": true,
}

var allowedEvidenceVerbs = map[string]bool{
	"answered_question": true, "predicted": true, "designed_experiment": true,
	"changed_variable": true, "started_trial": true, "paused_trial": true,
	"resumed_trial": true, "observed": true, "measured": true,
	"analyzed": true, "explained": true, "iterated": true, "reflected": true,
	"code_saved": true, "checkpoint_completed": true,
}

type DefinitionValidationError struct {
	Issues []dto.ValidationIssue
}

func (e *DefinitionValidationError) Error() string {
	return "experiment definition is not structurally valid"
}

type ExperimentService struct {
	experimentRepo *repository.ExperimentRepository
	labRepo        *repository.LabRepository
	enrollmentRepo *repository.EnrollmentRepository
}

func NewExperimentService(
	experimentRepo *repository.ExperimentRepository,
	labRepo *repository.LabRepository,
	enrollmentRepo *repository.EnrollmentRepository,
) *ExperimentService {
	return &ExperimentService{
		experimentRepo: experimentRepo,
		labRepo:        labRepo,
		enrollmentRepo: enrollmentRepo,
	}
}

func (s *ExperimentService) CreateVersion(
	ctx context.Context,
	labID, userID int64,
	userRole string,
	req *dto.CreateLabVersionRequest,
) (*dto.LabVersionResponse, int, error) {
	lab, err := s.labRepo.GetByID(ctx, labID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, http.StatusNotFound, fmt.Errorf("lab not found")
		}
		return nil, http.StatusInternalServerError, fmt.Errorf("get lab: %w", err)
	}
	if userRole != "ADMIN" && lab.CreatedBy != userID {
		return nil, http.StatusForbidden, fmt.Errorf("you don't have permission to version this lab")
	}
	if lab.LabType != "PLANT" && lab.LabType != "ROBOT" {
		return nil, http.StatusUnprocessableEntity, fmt.Errorf("experiment versions require a PLANT or ROBOT lab")
	}

	normalizeDefinition(&req.Definition)
	issues := validateStorageDefinition(req.Definition)
	if hasErrors(issues) {
		return nil, http.StatusUnprocessableEntity, &DefinitionValidationError{Issues: issues}
	}
	if req.Definition.Domain != lab.LabType {
		issue := dto.ValidationIssue{
			Severity: "ERROR", Code: "DOMAIN_MISMATCH", Path: "definition.domain",
			Message: fmt.Sprintf("definition domain %s must match lab type %s", req.Definition.Domain, lab.LabType),
		}
		return nil, http.StatusUnprocessableEntity, &DefinitionValidationError{Issues: []dto.ValidationIssue{issue}}
	}

	hash, err := definitionHash(req.Definition)
	if err != nil {
		return nil, http.StatusBadRequest, fmt.Errorf("hash definition: %w", err)
	}
	version, err := s.experimentRepo.CreateVersion(ctx, labID, userID, req, hash)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("create lab version: %w", err)
	}
	return version, http.StatusCreated, nil
}

func (s *ExperimentService) GetVersion(
	ctx context.Context,
	versionID, userID int64,
	userRole string,
) (*dto.LabVersionResponse, int, error) {
	version, err := s.experimentRepo.GetVersion(ctx, versionID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, http.StatusNotFound, fmt.Errorf("lab version not found")
		}
		return nil, http.StatusInternalServerError, fmt.Errorf("get lab version: %w", err)
	}
	allowed, err := s.canAccessVersion(ctx, version, userID, userRole)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	if !allowed {
		return nil, http.StatusForbidden, fmt.Errorf("you don't have permission to view this lab version")
	}
	return version, http.StatusOK, nil
}

func (s *ExperimentService) ListVersions(
	ctx context.Context,
	labID, userID int64,
	userRole string,
) ([]dto.LabVersionResponse, int, error) {
	if err := s.checkLabOwnership(ctx, labID, userID, userRole); err != nil {
		return nil, http.StatusForbidden, err
	}
	versions, err := s.experimentRepo.ListVersionsByLab(ctx, labID)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("list lab versions: %w", err)
	}
	return versions, http.StatusOK, nil
}

func (s *ExperimentService) GetPublishedVersion(
	ctx context.Context,
	labID, userID int64,
	userRole string,
) (*dto.LabVersionResponse, int, error) {
	version, err := s.experimentRepo.GetPublishedVersionByLab(ctx, labID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, http.StatusNotFound, fmt.Errorf("this lab has no published experiment version")
		}
		return nil, http.StatusInternalServerError, fmt.Errorf("get published lab version: %w", err)
	}
	allowed, err := s.canAccessVersion(ctx, version, userID, userRole)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	if !allowed {
		return nil, http.StatusForbidden, fmt.Errorf("you must enroll before opening this experiment")
	}
	return version, http.StatusOK, nil
}

func (s *ExperimentService) ValidateVersion(
	ctx context.Context,
	versionID, userID int64,
	userRole string,
) (*dto.LabVersionValidationResponse, int, error) {
	version, err := s.experimentRepo.GetVersion(ctx, versionID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, http.StatusNotFound, fmt.Errorf("lab version not found")
		}
		return nil, http.StatusInternalServerError, fmt.Errorf("get lab version: %w", err)
	}
	if err := s.checkLabOwnership(ctx, version.LabID, userID, userRole); err != nil {
		return nil, http.StatusForbidden, err
	}
	if version.Status == "PUBLISHED" || version.Status == "SUPERSEDED" {
		return nil, http.StatusConflict, fmt.Errorf("published or superseded versions are immutable")
	}

	issues := validatePublishDefinition(version.Definition)
	response := &dto.LabVersionValidationResponse{Valid: !hasErrors(issues), Issues: issues}
	if !response.Valid {
		return response, http.StatusOK, nil
	}
	if err := s.experimentRepo.MarkValidated(ctx, versionID); err != nil {
		return nil, http.StatusConflict, fmt.Errorf("mark version validated: %w", err)
	}
	return response, http.StatusOK, nil
}

func (s *ExperimentService) PublishVersion(
	ctx context.Context,
	versionID, userID int64,
	userRole string,
) (int, error) {
	version, err := s.experimentRepo.GetVersion(ctx, versionID)
	if err != nil {
		if err == sql.ErrNoRows {
			return http.StatusNotFound, fmt.Errorf("lab version not found")
		}
		return http.StatusInternalServerError, fmt.Errorf("get lab version: %w", err)
	}
	if err := s.checkLabOwnership(ctx, version.LabID, userID, userRole); err != nil {
		return http.StatusForbidden, err
	}
	if hasErrors(validatePublishDefinition(version.Definition)) {
		return http.StatusUnprocessableEntity, fmt.Errorf("lab version no longer passes publish validation")
	}
	if err := s.experimentRepo.PublishVersion(ctx, versionID); err != nil {
		if strings.Contains(err.Error(), "must be validated") {
			return http.StatusConflict, err
		}
		return http.StatusInternalServerError, fmt.Errorf("publish lab version: %w", err)
	}
	return http.StatusOK, nil
}

func (s *ExperimentService) CreateRun(
	ctx context.Context,
	versionID, userID int64,
	userRole string,
	req *dto.CreateRunRequest,
) (*dto.RunResponse, int, error) {
	version, err := s.experimentRepo.GetVersion(ctx, versionID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, http.StatusNotFound, fmt.Errorf("lab version not found")
		}
		return nil, http.StatusInternalServerError, err
	}
	if version.Status != "PUBLISHED" {
		return nil, http.StatusConflict, fmt.Errorf("only published lab versions can be started")
	}
	allowed, err := s.canStartRun(ctx, version.LabID, userID, userRole)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	if !allowed {
		return nil, http.StatusForbidden, fmt.Errorf("you must be enrolled in this lab")
	}
	run, err := s.experimentRepo.CreateRun(ctx, versionID, userID, req.IdempotencyKey)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("create lab run: %w", err)
	}
	return run, http.StatusCreated, nil
}

func (s *ExperimentService) GetRun(
	ctx context.Context,
	runID, userID int64,
	userRole string,
) (*dto.RunResponse, int, error) {
	run, status, err := s.getAccessibleRun(ctx, runID, userID, userRole)
	return run, status, err
}

func (s *ExperimentService) CompleteRun(
	ctx context.Context,
	runID, userID int64,
) (*dto.RunResponse, int, error) {
	run, err := s.experimentRepo.GetRun(ctx, runID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, http.StatusNotFound, fmt.Errorf("lab run not found")
		}
		return nil, http.StatusInternalServerError, err
	}
	if run.UserID != userID {
		return nil, http.StatusForbidden, fmt.Errorf("only the run owner can complete it")
	}
	if run.Status == "COMPLETED" {
		return run, http.StatusOK, nil
	}
	version, err := s.experimentRepo.GetVersion(ctx, run.LabVersionID)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	events, err := s.experimentRepo.ListEvidence(ctx, runID, 0, 500)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	evidence := make(map[string]map[string]bool)
	trialIDs := make(map[int64]bool)
	for _, event := range events {
		node, _ := event.Context["workflow_node"].(string)
		if evidence[node] == nil {
			evidence[node] = make(map[string]bool)
		}
		evidence[node][event.Object.Type] = true
		if event.Object.Type == "simulation_run" && event.TrialID != nil {
			trialIDs[*event.TrialID] = true
		}
	}
	missing := make([]string, 0)
	hasIterationStep := false
	for _, node := range version.Definition.Nodes {
		if node.Type == "ITERATE" {
			hasIterationStep = true
		}
		for _, required := range node.RequiredEvidence {
			if !evidence[node.Key][required] {
				missing = append(missing, node.Key+":"+required)
			}
		}
	}
	if hasIterationStep && len(trialIDs) < 2 {
		missing = append(missing, "iterate:second_trial")
	}
	if len(missing) > 0 {
		return nil, http.StatusUnprocessableEntity, fmt.Errorf("required evidence is missing: %s", strings.Join(missing, ", "))
	}
	completed, err := s.experimentRepo.CompleteRun(ctx, runID, userID)
	if err != nil {
		return nil, http.StatusConflict, fmt.Errorf("complete lab run: %w", err)
	}
	return completed, http.StatusOK, nil
}

func (s *ExperimentService) ListLabRuns(
	ctx context.Context,
	labID, userID int64,
	userRole, runStatus string,
	page, pageSize int,
) (*dto.ListResponse, int, error) {
	if err := s.checkLabOwnership(ctx, labID, userID, userRole); err != nil {
		return nil, http.StatusForbidden, err
	}
	if runStatus != "" && runStatus != "ACTIVE" && runStatus != "COMPLETED" && runStatus != "ABANDONED" {
		return nil, http.StatusBadRequest, fmt.Errorf("status must be ACTIVE, COMPLETED or ABANDONED")
	}
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}
	runs, total, err := s.experimentRepo.ListRunsByLab(
		ctx, labID, runStatus, pageSize, (page-1)*pageSize,
	)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("list lab runs: %w", err)
	}
	return dto.NewListResponse(runs, page, pageSize, total), http.StatusOK, nil
}

func (s *ExperimentService) CreateTrial(
	ctx context.Context,
	runID, userID int64,
	req *dto.CreateTrialRequest,
) (*dto.TrialResponse, int, error) {
	run, err := s.experimentRepo.GetRun(ctx, runID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, http.StatusNotFound, fmt.Errorf("lab run not found")
		}
		return nil, http.StatusInternalServerError, err
	}
	if run.UserID != userID {
		return nil, http.StatusForbidden, fmt.Errorf("only the run owner can create a trial")
	}
	seed, err := experimentSeed(req.Seed)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	trial, err := s.experimentRepo.CreateTrial(ctx, runID, userID, seed, req.ConfigSnapshot)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, http.StatusConflict, fmt.Errorf("run is not active or not owned by the learner")
		}
		return nil, http.StatusInternalServerError, fmt.Errorf("create trial: %w", err)
	}
	return trial, http.StatusCreated, nil
}

func (s *ExperimentService) AppendEvidence(
	ctx context.Context,
	runID, userID int64,
	req *dto.AppendEvidenceRequest,
) (*dto.EvidenceEventResponse, int, error) {
	if !allowedEvidenceVerbs[req.Verb] {
		return nil, http.StatusUnprocessableEntity, fmt.Errorf("unsupported evidence verb: %s", req.Verb)
	}
	if !identifierPattern.MatchString(req.Object.Type) {
		return nil, http.StatusUnprocessableEntity, fmt.Errorf("evidence object type must be a stable lowercase identifier")
	}
	if req.WorkflowNodeKey != "" && !identifierPattern.MatchString(req.WorkflowNodeKey) {
		return nil, http.StatusUnprocessableEntity, fmt.Errorf("workflow_node_key must be a stable lowercase identifier")
	}
	payload, err := json.Marshal(req)
	if err != nil {
		return nil, http.StatusBadRequest, fmt.Errorf("encode evidence payload: %w", err)
	}
	if len(payload) > maxEvidencePayloadBytes {
		return nil, http.StatusRequestEntityTooLarge, fmt.Errorf("evidence payload exceeds %d bytes", maxEvidencePayloadBytes)
	}

	run, err := s.experimentRepo.GetRun(ctx, runID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, http.StatusNotFound, fmt.Errorf("lab run not found")
		}
		return nil, http.StatusInternalServerError, err
	}
	if run.UserID != userID {
		return nil, http.StatusForbidden, fmt.Errorf("only the run owner can append evidence")
	}
	if req.Context == nil {
		req.Context = map[string]interface{}{}
	}
	if req.WorkflowNodeKey != "" {
		req.Context["workflow_node"] = req.WorkflowNodeKey
	}
	event, err := s.experimentRepo.AppendEvidence(ctx, runID, userID, "LEARNER", req)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, http.StatusConflict, fmt.Errorf("run is inactive or workflow node is invalid")
		}
		return nil, http.StatusInternalServerError, fmt.Errorf("append evidence: %w", err)
	}
	return event, http.StatusCreated, nil
}

func (s *ExperimentService) ListEvidence(
	ctx context.Context,
	runID, userID int64,
	userRole string,
	afterSeq int64,
	limit int,
) ([]dto.EvidenceEventResponse, int, error) {
	if afterSeq < 0 {
		afterSeq = 0
	}
	if limit < 1 || limit > 500 {
		limit = 200
	}
	if _, status, err := s.getAccessibleRun(ctx, runID, userID, userRole); err != nil {
		return nil, status, err
	}
	events, err := s.experimentRepo.ListEvidence(ctx, runID, afterSeq, limit)
	if err != nil {
		return nil, http.StatusInternalServerError, fmt.Errorf("list evidence: %w", err)
	}
	return events, http.StatusOK, nil
}

func (s *ExperimentService) getAccessibleRun(
	ctx context.Context,
	runID, userID int64,
	userRole string,
) (*dto.RunResponse, int, error) {
	run, err := s.experimentRepo.GetRun(ctx, runID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, http.StatusNotFound, fmt.Errorf("lab run not found")
		}
		return nil, http.StatusInternalServerError, err
	}
	if run.UserID == userID || userRole == "ADMIN" {
		return run, http.StatusOK, nil
	}
	creatorID, err := s.labRepo.GetCreatorID(ctx, run.LabID)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	if creatorID != userID {
		return nil, http.StatusForbidden, fmt.Errorf("you don't have permission to view this lab run")
	}
	return run, http.StatusOK, nil
}

func (s *ExperimentService) canAccessVersion(
	ctx context.Context,
	version *dto.LabVersionResponse,
	userID int64,
	userRole string,
) (bool, error) {
	if userRole == "ADMIN" || version.CreatedBy == userID {
		return true, nil
	}
	if version.Status != "PUBLISHED" {
		return false, nil
	}
	return s.enrollmentRepo.IsEnrolled(ctx, version.LabID, userID)
}

func (s *ExperimentService) canStartRun(
	ctx context.Context,
	labID, userID int64,
	userRole string,
) (bool, error) {
	if userRole == "ADMIN" {
		return true, nil
	}
	creatorID, err := s.labRepo.GetCreatorID(ctx, labID)
	if err != nil {
		return false, err
	}
	if creatorID == userID {
		return true, nil
	}
	return s.enrollmentRepo.IsEnrolled(ctx, labID, userID)
}

func (s *ExperimentService) checkLabOwnership(
	ctx context.Context,
	labID, userID int64,
	userRole string,
) error {
	if userRole == "ADMIN" {
		return nil
	}
	creatorID, err := s.labRepo.GetCreatorID(ctx, labID)
	if err != nil {
		return fmt.Errorf("lab not found")
	}
	if creatorID != userID {
		return fmt.Errorf("you don't have permission to modify this lab")
	}
	return nil
}

func normalizeDefinition(definition *dto.ExperimentDefinitionRequest) {
	if definition.WorkflowSchemaVersion == 0 {
		definition.WorkflowSchemaVersion = 1
	}
	if definition.LearningObjectives == nil {
		definition.LearningObjectives = []string{}
	}
	if definition.Config == nil {
		definition.Config = map[string]interface{}{}
	}
	if definition.Nodes == nil {
		definition.Nodes = []dto.WorkflowNodeRequest{}
	}
	if definition.Edges == nil {
		definition.Edges = []dto.WorkflowEdgeRequest{}
	}
	if definition.Variables == nil {
		definition.Variables = []dto.ExperimentVariableRequest{}
	}
	for i := range definition.Nodes {
		if definition.Nodes[i].Config == nil {
			definition.Nodes[i].Config = map[string]interface{}{}
		}
		if definition.Nodes[i].RequiredEvidence == nil {
			definition.Nodes[i].RequiredEvidence = []string{}
		}
	}
}

func validateStorageDefinition(definition dto.ExperimentDefinitionRequest) []dto.ValidationIssue {
	issues := make([]dto.ValidationIssue, 0)
	add := func(code, path, message string) {
		issues = append(issues, dto.ValidationIssue{Severity: "ERROR", Code: code, Path: path, Message: message})
	}
	if definition.Domain != "PLANT" && definition.Domain != "ROBOT" {
		add("INVALID_DOMAIN", "definition.domain", "domain must be PLANT or ROBOT")
	}
	if definition.InquiryLevel != "STRUCTURED" && definition.InquiryLevel != "GUIDED" && definition.InquiryLevel != "OPEN_INQUIRY" {
		add("INVALID_INQUIRY_LEVEL", "definition.inquiry_level", "inquiry_level must be STRUCTURED, GUIDED or OPEN_INQUIRY")
	}
	if definition.WorkflowSchemaVersion < 1 {
		add("INVALID_SCHEMA_VERSION", "definition.workflow_schema_version", "workflow_schema_version must be positive")
	}
	if strings.TrimSpace(definition.ModelVersion) == "" {
		add("MODEL_VERSION_REQUIRED", "definition.model_version", "model_version is required")
	}

	nodes := make(map[string]dto.WorkflowNodeRequest, len(definition.Nodes))
	for i, node := range definition.Nodes {
		path := fmt.Sprintf("definition.nodes[%d]", i)
		if !identifierPattern.MatchString(node.Key) {
			add("INVALID_NODE_KEY", path+".key", "node key must be a stable lowercase identifier")
		}
		if _, exists := nodes[node.Key]; exists {
			add("DUPLICATE_NODE_KEY", path+".key", "node key must be unique")
		}
		nodes[node.Key] = node
		if !allowedNodeTypes[node.Type] {
			add("INVALID_NODE_TYPE", path+".type", "unsupported workflow node type")
		}
		if strings.TrimSpace(node.Title) == "" {
			add("NODE_TITLE_REQUIRED", path+".title", "node title is required")
		}
		if node.OrderHint < 0 {
			add("INVALID_ORDER_HINT", path+".order_hint", "order_hint cannot be negative")
		}
	}
	for i, edge := range definition.Edges {
		path := fmt.Sprintf("definition.edges[%d]", i)
		if _, exists := nodes[edge.From]; !exists {
			add("EDGE_SOURCE_MISSING", path+".from", "edge source node does not exist")
		}
		if _, exists := nodes[edge.To]; !exists {
			add("EDGE_TARGET_MISSING", path+".to", "edge target node does not exist")
		}
		if edge.From == edge.To {
			add("SELF_EDGE", path, "self-referencing workflow edges are not supported")
		}
		condition := edge.ConditionExpression
		if condition != "" && condition != "always" {
			add("UNSUPPORTED_CONDITION", path+".condition_expression", "the MVP supports only the 'always' condition")
		}
	}

	variables := make(map[string]bool, len(definition.Variables))
	for i, variable := range definition.Variables {
		path := fmt.Sprintf("definition.variables[%d]", i)
		if !identifierPattern.MatchString(variable.Key) {
			add("INVALID_VARIABLE_KEY", path+".key", "variable key must be a stable lowercase identifier")
		}
		if variables[variable.Key] {
			add("DUPLICATE_VARIABLE_KEY", path+".key", "variable key must be unique")
		}
		variables[variable.Key] = true
		if variable.Role != "INDEPENDENT" && variable.Role != "DEPENDENT" && variable.Role != "CONTROLLED" {
			add("INVALID_VARIABLE_ROLE", path+".role", "unsupported experiment variable role")
		}
		if variable.DataType != "NUMBER" && variable.DataType != "INTEGER" && variable.DataType != "BOOLEAN" && variable.DataType != "STRING" {
			add("INVALID_VARIABLE_TYPE", path+".data_type", "unsupported experiment variable data type")
		}
		if variable.MinValue != nil && variable.MaxValue != nil && *variable.MinValue > *variable.MaxValue {
			add("INVALID_VARIABLE_RANGE", path, "min_value cannot exceed max_value")
		}
	}
	return issues
}

func validatePublishDefinition(definition dto.ExperimentDefinitionRequest) []dto.ValidationIssue {
	issues := validateStorageDefinition(definition)
	addError := func(code, path, message string) {
		issues = append(issues, dto.ValidationIssue{Severity: "ERROR", Code: code, Path: path, Message: message})
	}
	addWarning := func(code, path, message string) {
		issues = append(issues, dto.ValidationIssue{Severity: "WARNING", Code: code, Path: path, Message: message})
	}

	if len(definition.LearningObjectives) == 0 {
		addError("LEARNING_OBJECTIVE_REQUIRED", "definition.learning_objectives", "at least one learning objective is required")
	}
	for i, objective := range definition.LearningObjectives {
		if strings.TrimSpace(objective) == "" {
			addError("EMPTY_LEARNING_OBJECTIVE", fmt.Sprintf("definition.learning_objectives[%d]", i), "learning objective cannot be empty")
		}
	}
	if len(definition.Nodes) == 0 {
		addError("WORKFLOW_REQUIRED", "definition.nodes", "workflow must contain nodes")
		return issues
	}

	typeCount := make(map[string]int)
	indegree := make(map[string]int)
	outdegree := make(map[string]int)
	adjacency := make(map[string][]string)
	for _, node := range definition.Nodes {
		typeCount[node.Type]++
		indegree[node.Key] = 0
		outdegree[node.Key] = 0
		if requiresEvidence(node.Type) && len(node.RequiredEvidence) == 0 {
			addError("REQUIRED_EVIDENCE_MISSING", "definition.nodes."+node.Key+".required_evidence", "this STEM step must declare required evidence")
		}
	}
	for _, edge := range definition.Edges {
		indegree[edge.To]++
		outdegree[edge.From]++
		adjacency[edge.From] = append(adjacency[edge.From], edge.To)
	}
	for _, requiredType := range []string{"PREDICTION", "RUN", "ANALYZE", "EXPLAIN", "ITERATE"} {
		if typeCount[requiredType] == 0 {
			addError("STEM_STEP_MISSING", "definition.nodes", "workflow requires a "+requiredType+" step")
		}
	}

	starts := make([]string, 0)
	terminalCount := 0
	for _, node := range definition.Nodes {
		if indegree[node.Key] == 0 {
			starts = append(starts, node.Key)
		}
		if outdegree[node.Key] == 0 {
			terminalCount++
		}
	}
	if len(starts) != 1 {
		addError("WORKFLOW_START_COUNT", "definition.edges", "workflow must have exactly one start node")
	}
	if terminalCount == 0 {
		addError("WORKFLOW_TERMINAL_REQUIRED", "definition.edges", "workflow must have at least one terminal node")
	}
	if len(starts) > 0 {
		visited := map[string]bool{}
		queue := []string{starts[0]}
		for len(queue) > 0 {
			current := queue[0]
			queue = queue[1:]
			if visited[current] {
				continue
			}
			visited[current] = true
			queue = append(queue, adjacency[current]...)
		}
		for _, node := range definition.Nodes {
			if !visited[node.Key] {
				addError("UNREACHABLE_NODE", "definition.nodes."+node.Key, "workflow node is unreachable from the start")
			}
		}
	}

	roles := map[string]int{}
	for i, variable := range definition.Variables {
		roles[variable.Role]++
		path := fmt.Sprintf("definition.variables[%d]", i)
		if (variable.DataType == "NUMBER" || variable.DataType == "INTEGER") && strings.TrimSpace(variable.Unit) == "" {
			addError("VARIABLE_UNIT_REQUIRED", path+".unit", "numeric variables require a unit; use '1' for dimensionless values")
		}
		if (variable.DataType == "NUMBER" || variable.DataType == "INTEGER") && strings.TrimSpace(variable.SourceID) == "" {
			addWarning("VARIABLE_SOURCE_RECOMMENDED", path+".source_id", "numeric scientific variables should cite a source or model card")
		}
	}
	for _, role := range []string{"INDEPENDENT", "DEPENDENT", "CONTROLLED"} {
		if roles[role] == 0 {
			addError("VARIABLE_ROLE_MISSING", "definition.variables", "experiment requires a "+role+" variable")
		}
	}
	return issues
}

func requiresEvidence(nodeType string) bool {
	switch nodeType {
	case "PREDICTION", "MEASURE", "ANALYZE", "EXPLAIN", "ITERATE", "REFLECT":
		return true
	default:
		return false
	}
}

func hasErrors(issues []dto.ValidationIssue) bool {
	for _, issue := range issues {
		if issue.Severity == "ERROR" {
			return true
		}
	}
	return false
}

func definitionHash(definition dto.ExperimentDefinitionRequest) (string, error) {
	data, err := json.Marshal(definition)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(data)
	return hex.EncodeToString(digest[:]), nil
}

func experimentSeed(requested *int64) (int64, error) {
	if requested != nil {
		return *requested, nil
	}
	// Keep generated seeds inside JavaScript's exact integer range because the
	// browser concept engine receives them through JSON and must replay exactly.
	value, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 53))
	if err != nil {
		return 0, fmt.Errorf("generate experiment seed: %w", err)
	}
	return value.Int64(), nil
}
