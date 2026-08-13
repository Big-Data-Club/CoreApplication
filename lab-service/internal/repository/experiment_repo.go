package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"

	"lab-service/internal/dto"
)

type ExperimentRepository struct{ db *sql.DB }

func NewExperimentRepository(db *sql.DB) *ExperimentRepository {
	return &ExperimentRepository{db: db}
}

func (r *ExperimentRepository) CreateVersion(
	ctx context.Context,
	labID, userID int64,
	req *dto.CreateLabVersionRequest,
	definitionHash string,
) (*dto.LabVersionResponse, error) {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, fmt.Errorf("begin create lab version: %w", err)
	}
	defer tx.Rollback()

	var labType string
	if err := tx.QueryRowContext(ctx, "SELECT lab_type FROM labs WHERE id = $1 FOR UPDATE", labID).Scan(&labType); err != nil {
		return nil, fmt.Errorf("lock lab for version: %w", err)
	}
	if labType != req.Definition.Domain {
		return nil, fmt.Errorf("definition domain %s does not match lab type %s", req.Definition.Domain, labType)
	}

	definitionJSON, err := json.Marshal(req.Definition)
	if err != nil {
		return nil, fmt.Errorf("marshal experiment definition: %w", err)
	}
	objectivesJSON, err := json.Marshal(req.Definition.LearningObjectives)
	if err != nil {
		return nil, fmt.Errorf("marshal learning objectives: %w", err)
	}
	configJSON, err := json.Marshal(nonNilMap(req.Definition.Config))
	if err != nil {
		return nil, fmt.Errorf("marshal experiment config: %w", err)
	}

	var resp dto.LabVersionResponse
	var definitionRaw []byte
	err = tx.QueryRowContext(ctx,
		`INSERT INTO lab_versions (
			lab_id, version_number, definition_hash, definition_snapshot, created_by
		) VALUES (
			$1,
			COALESCE((SELECT MAX(version_number) + 1 FROM lab_versions WHERE lab_id = $1), 1),
			$2, $3, $4
		)
		RETURNING id, lab_id, version_number, status, definition_hash,
			definition_snapshot, created_by, validated_at, published_at, created_at, updated_at`,
		labID, definitionHash, definitionJSON, userID,
	).Scan(
		&resp.ID, &resp.LabID, &resp.VersionNumber, &resp.Status, &resp.DefinitionHash,
		&definitionRaw, &resp.CreatedBy, &resp.ValidatedAt, &resp.PublishedAt,
		&resp.CreatedAt, &resp.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("insert lab version: %w", err)
	}

	_, err = tx.ExecContext(ctx,
		`INSERT INTO experiment_definitions (
			lab_version_id, domain, inquiry_level, workflow_schema_version,
			model_version, learning_objectives, config
		) VALUES ($1,$2,$3,$4,$5,$6,$7)`,
		resp.ID, req.Definition.Domain, req.Definition.InquiryLevel,
		req.Definition.WorkflowSchemaVersion, req.Definition.ModelVersion,
		objectivesJSON, configJSON,
	)
	if err != nil {
		return nil, fmt.Errorf("insert experiment definition: %w", err)
	}

	for _, node := range req.Definition.Nodes {
		nodeConfig, marshalErr := json.Marshal(nonNilMap(node.Config))
		if marshalErr != nil {
			return nil, fmt.Errorf("marshal workflow node %s: %w", node.Key, marshalErr)
		}
		requiredEvidence, marshalErr := json.Marshal(nonNilStrings(node.RequiredEvidence))
		if marshalErr != nil {
			return nil, fmt.Errorf("marshal required evidence for %s: %w", node.Key, marshalErr)
		}
		_, err = tx.ExecContext(ctx,
			`INSERT INTO workflow_nodes (
				lab_version_id, node_key, node_type, title, config, required_evidence, order_hint
			) VALUES ($1,$2,$3,$4,$5,$6,$7)`,
			resp.ID, node.Key, node.Type, node.Title, nodeConfig, requiredEvidence, node.OrderHint,
		)
		if err != nil {
			return nil, fmt.Errorf("insert workflow node %s: %w", node.Key, err)
		}
	}

	for _, edge := range req.Definition.Edges {
		condition := edge.ConditionExpression
		if condition == "" {
			condition = "always"
		}
		_, err = tx.ExecContext(ctx,
			`INSERT INTO workflow_edges (
				lab_version_id, from_node_key, to_node_key, condition_expression, priority
			) VALUES ($1,$2,$3,$4,$5)`,
			resp.ID, edge.From, edge.To, condition, edge.Priority,
		)
		if err != nil {
			return nil, fmt.Errorf("insert workflow edge %s -> %s: %w", edge.From, edge.To, err)
		}
	}

	for _, variable := range req.Definition.Variables {
		defaultJSON, marshalErr := json.Marshal(variable.DefaultValue)
		if marshalErr != nil {
			return nil, fmt.Errorf("marshal default value for %s: %w", variable.Key, marshalErr)
		}
		_, err = tx.ExecContext(ctx,
			`INSERT INTO experiment_variables (
				lab_version_id, variable_key, display_name, variable_role, data_type,
				unit, min_value, max_value, default_value, source_id
			) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`,
			resp.ID, variable.Key, variable.DisplayName, variable.Role, variable.DataType,
			variable.Unit, variable.MinValue, variable.MaxValue, defaultJSON, variable.SourceID,
		)
		if err != nil {
			return nil, fmt.Errorf("insert experiment variable %s: %w", variable.Key, err)
		}
	}

	if err := json.Unmarshal(definitionRaw, &resp.Definition); err != nil {
		return nil, fmt.Errorf("decode stored experiment definition: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("commit lab version: %w", err)
	}
	return &resp, nil
}

func (r *ExperimentRepository) GetVersion(ctx context.Context, versionID int64) (*dto.LabVersionResponse, error) {
	var resp dto.LabVersionResponse
	var definitionRaw []byte
	err := r.db.QueryRowContext(ctx,
		`SELECT id, lab_id, version_number, status, definition_hash,
			definition_snapshot, created_by, validated_at, published_at, created_at, updated_at
		FROM lab_versions WHERE id = $1`, versionID,
	).Scan(
		&resp.ID, &resp.LabID, &resp.VersionNumber, &resp.Status, &resp.DefinitionHash,
		&definitionRaw, &resp.CreatedBy, &resp.ValidatedAt, &resp.PublishedAt,
		&resp.CreatedAt, &resp.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(definitionRaw, &resp.Definition); err != nil {
		return nil, fmt.Errorf("decode experiment definition: %w", err)
	}
	return &resp, nil
}

func (r *ExperimentRepository) MarkValidated(ctx context.Context, versionID int64) error {
	result, err := r.db.ExecContext(ctx,
		`UPDATE lab_versions
		SET status = 'VALIDATED', validated_at = NOW(), updated_at = NOW()
		WHERE id = $1 AND status IN ('DRAFT', 'VALIDATED')`, versionID)
	if err != nil {
		return err
	}
	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if rows == 0 {
		return sql.ErrNoRows
	}
	return nil
}

func (r *ExperimentRepository) PublishVersion(ctx context.Context, versionID int64) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin publish version: %w", err)
	}
	defer tx.Rollback()

	var labID int64
	var status string
	if err := tx.QueryRowContext(ctx,
		"SELECT lab_id, status FROM lab_versions WHERE id = $1 FOR UPDATE", versionID,
	).Scan(&labID, &status); err != nil {
		return err
	}
	var lockedLabID int64
	if err := tx.QueryRowContext(ctx,
		"SELECT id FROM labs WHERE id = $1 FOR UPDATE", labID,
	).Scan(&lockedLabID); err != nil {
		return err
	}
	if status == "PUBLISHED" {
		return tx.Commit()
	}
	if status != "VALIDATED" {
		return fmt.Errorf("lab version must be validated before publishing")
	}

	if _, err := tx.ExecContext(ctx,
		`UPDATE lab_versions SET status = 'SUPERSEDED', updated_at = NOW()
		WHERE lab_id = $1 AND status = 'PUBLISHED'`, labID); err != nil {
		return fmt.Errorf("supersede previous version: %w", err)
	}
	if _, err := tx.ExecContext(ctx,
		`UPDATE lab_versions
		SET status = 'PUBLISHED', published_at = NOW(), updated_at = NOW()
		WHERE id = $1`, versionID); err != nil {
		return fmt.Errorf("publish lab version: %w", err)
	}
	if _, err := tx.ExecContext(ctx,
		`UPDATE labs SET status = 'PUBLISHED', published_at = NOW(), updated_at = NOW()
		WHERE id = $1`, labID); err != nil {
		return fmt.Errorf("publish lab: %w", err)
	}
	return tx.Commit()
}

func (r *ExperimentRepository) CreateRun(
	ctx context.Context,
	labVersionID, userID int64,
	idempotencyKey string,
) (*dto.RunResponse, error) {
	var resp dto.RunResponse
	err := r.db.QueryRowContext(ctx,
		`WITH inserted AS (
			INSERT INTO lab_runs (lab_version_id, user_id, idempotency_key)
			VALUES ($1, $2, $3)
			ON CONFLICT (lab_version_id, user_id, idempotency_key)
			DO UPDATE SET idempotency_key = EXCLUDED.idempotency_key
			RETURNING *
		)
		SELECT r.id, v.lab_id, r.lab_version_id, v.version_number, r.user_id,
			r.status, r.current_node_key, r.last_event_seq, r.started_at, r.ended_at, r.updated_at
		FROM inserted r JOIN lab_versions v ON v.id = r.lab_version_id`,
		labVersionID, userID, idempotencyKey,
	).Scan(
		&resp.ID, &resp.LabID, &resp.LabVersionID, &resp.LabVersionNumber,
		&resp.UserID, &resp.Status, &resp.CurrentNodeKey, &resp.LastEventSeq,
		&resp.StartedAt, &resp.EndedAt, &resp.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	return &resp, nil
}

func (r *ExperimentRepository) GetRun(ctx context.Context, runID int64) (*dto.RunResponse, error) {
	var resp dto.RunResponse
	err := r.db.QueryRowContext(ctx,
		`SELECT r.id, v.lab_id, r.lab_version_id, v.version_number, r.user_id,
			r.status, r.current_node_key, r.last_event_seq, r.started_at, r.ended_at, r.updated_at
		FROM lab_runs r
		JOIN lab_versions v ON v.id = r.lab_version_id
		WHERE r.id = $1`, runID,
	).Scan(
		&resp.ID, &resp.LabID, &resp.LabVersionID, &resp.LabVersionNumber,
		&resp.UserID, &resp.Status, &resp.CurrentNodeKey, &resp.LastEventSeq,
		&resp.StartedAt, &resp.EndedAt, &resp.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	return &resp, nil
}

func (r *ExperimentRepository) ListRunsByLab(
	ctx context.Context,
	labID int64,
	status string,
	limit, offset int,
) ([]dto.RunSummaryResponse, int, error) {
	statusFilter := ""
	args := []interface{}{labID}
	if status != "" {
		statusFilter = " AND r.status = $2"
		args = append(args, status)
	}

	var total int
	if err := r.db.QueryRowContext(ctx,
		`SELECT COUNT(*)
		FROM lab_runs r JOIN lab_versions v ON v.id = r.lab_version_id
		WHERE v.lab_id = $1`+statusFilter,
		args...,
	).Scan(&total); err != nil {
		return nil, 0, err
	}

	limitPosition := len(args) + 1
	offsetPosition := limitPosition + 1
	args = append(args, limit, offset)
	rows, err := r.db.QueryContext(ctx,
		fmt.Sprintf(`SELECT r.id, v.lab_id, r.lab_version_id, v.version_number, r.user_id,
			r.status, r.current_node_key, r.last_event_seq, r.started_at, r.ended_at,
			r.updated_at, u.full_name, u.email, COUNT(t.id)
		FROM lab_runs r
		JOIN lab_versions v ON v.id = r.lab_version_id
		JOIN users u ON u.id = r.user_id
		LEFT JOIN experiment_trials t ON t.run_id = r.id
		WHERE v.lab_id = $1%s
		GROUP BY r.id, v.lab_id, v.version_number, u.full_name, u.email
		ORDER BY r.updated_at DESC
		LIMIT $%d OFFSET $%d`, statusFilter, limitPosition, offsetPosition),
		args...,
	)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	runs := make([]dto.RunSummaryResponse, 0)
	for rows.Next() {
		var run dto.RunSummaryResponse
		if err := rows.Scan(
			&run.ID, &run.LabID, &run.LabVersionID, &run.LabVersionNumber,
			&run.UserID, &run.Status, &run.CurrentNodeKey, &run.LastEventSeq,
			&run.StartedAt, &run.EndedAt, &run.UpdatedAt, &run.LearnerName,
			&run.LearnerEmail, &run.TrialCount,
		); err != nil {
			return nil, 0, err
		}
		runs = append(runs, run)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, err
	}
	return runs, total, nil
}

func (r *ExperimentRepository) CreateTrial(
	ctx context.Context,
	runID, userID, seed int64,
	config map[string]interface{},
) (*dto.TrialResponse, error) {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, fmt.Errorf("begin create trial: %w", err)
	}
	defer tx.Rollback()

	var modelVersion, runStatus string
	if err := tx.QueryRowContext(ctx,
		`SELECT d.model_version, r.status
		FROM lab_runs r
		JOIN experiment_definitions d ON d.lab_version_id = r.lab_version_id
		WHERE r.id = $1 AND r.user_id = $2
		FOR UPDATE OF r`, runID, userID,
	).Scan(&modelVersion, &runStatus); err != nil {
		return nil, err
	}
	if runStatus != "ACTIVE" {
		return nil, fmt.Errorf("cannot create a trial for a %s run", runStatus)
	}

	configJSON, err := json.Marshal(nonNilMap(config))
	if err != nil {
		return nil, fmt.Errorf("marshal trial config: %w", err)
	}
	var resp dto.TrialResponse
	var configRaw []byte
	err = tx.QueryRowContext(ctx,
		`INSERT INTO experiment_trials (
			run_id, trial_number, seed, model_version, config_snapshot
		) VALUES (
			$1,
			COALESCE((SELECT MAX(trial_number) + 1 FROM experiment_trials WHERE run_id = $1), 1),
			$2, $3, $4
		)
		RETURNING id, run_id, trial_number, seed, model_version, config_snapshot,
			status, started_at, ended_at, created_at`,
		runID, seed, modelVersion, configJSON,
	).Scan(
		&resp.ID, &resp.RunID, &resp.TrialNumber, &resp.Seed, &resp.ModelVersion,
		&configRaw, &resp.Status, &resp.StartedAt, &resp.EndedAt, &resp.CreatedAt,
	)
	if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(configRaw, &resp.ConfigSnapshot); err != nil {
		return nil, fmt.Errorf("decode trial config: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return nil, err
	}
	return &resp, nil
}

func (r *ExperimentRepository) AppendEvidence(
	ctx context.Context,
	runID, actorID int64,
	actorType string,
	req *dto.AppendEvidenceRequest,
) (*dto.EvidenceEventResponse, error) {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, fmt.Errorf("begin append evidence: %w", err)
	}
	defer tx.Rollback()

	// Serialize appends per run so concurrent retries with the same client_event_id
	// remain idempotent and cannot consume two sequence numbers.
	var lockedRunID int64
	if err := tx.QueryRowContext(ctx,
		"SELECT id FROM lab_runs WHERE id = $1 AND user_id = $2 FOR UPDATE",
		runID, actorID,
	).Scan(&lockedRunID); err != nil {
		return nil, err
	}

	if existing, err := getEvidenceByClientID(ctx, tx, runID, actorID, req.ClientEventID); err == nil {
		return existing, tx.Commit()
	} else if err != sql.ErrNoRows {
		return nil, err
	}

	var seqNo int64
	err = tx.QueryRowContext(ctx,
		`UPDATE lab_runs r
		SET last_event_seq = last_event_seq + 1,
			current_node_key = COALESCE(NULLIF($3, ''), current_node_key),
			updated_at = NOW()
		WHERE r.id = $1 AND r.user_id = $2 AND r.status = 'ACTIVE'
			AND ($3 = '' OR EXISTS (
				SELECT 1 FROM workflow_nodes n
				WHERE n.lab_version_id = r.lab_version_id AND n.node_key = $3
			))
		RETURNING last_event_seq`, runID, actorID,
		req.WorkflowNodeKey,
	).Scan(&seqNo)
	if err != nil {
		return nil, err
	}

	objectJSON, err := json.Marshal(req.Object)
	if err != nil {
		return nil, fmt.Errorf("marshal evidence object: %w", err)
	}
	resultJSON, err := json.Marshal(nonNilMap(req.Result))
	if err != nil {
		return nil, fmt.Errorf("marshal evidence result: %w", err)
	}
	contextJSON, err := json.Marshal(nonNilMap(req.Context))
	if err != nil {
		return nil, fmt.Errorf("marshal evidence context: %w", err)
	}

	var resp dto.EvidenceEventResponse
	var objectRaw, resultRaw, contextRaw []byte
	err = tx.QueryRowContext(ctx,
		`INSERT INTO evidence_events (
			client_event_id, run_id, trial_id, seq_no, actor_id, actor_type,
			verb, object_data, result_data, context_data, sim_time_ms
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
		RETURNING event_id::text, client_event_id::text, schema_version, run_id, trial_id,
			seq_no, actor_id, actor_type, verb, object_data, result_data, context_data,
			sim_time_ms, occurred_at, ingested_at`,
		req.ClientEventID, runID, req.TrialID, seqNo, actorID, actorType,
		req.Verb, objectJSON, resultJSON, contextJSON, req.SimTimeMs,
	).Scan(
		&resp.EventID, &resp.ClientEventID, &resp.SchemaVersion, &resp.RunID,
		&resp.TrialID, &resp.SeqNo, &resp.ActorID, &resp.ActorType, &resp.Verb,
		&objectRaw, &resultRaw, &contextRaw, &resp.SimTimeMs,
		&resp.OccurredAt, &resp.IngestedAt,
	)
	if err != nil {
		return nil, err
	}
	if err := decodeEvidenceJSON(&resp, objectRaw, resultRaw, contextRaw); err != nil {
		return nil, err
	}
	if err := tx.Commit(); err != nil {
		return nil, err
	}
	return &resp, nil
}

func (r *ExperimentRepository) ListEvidence(
	ctx context.Context,
	runID, afterSeq int64,
	limit int,
) ([]dto.EvidenceEventResponse, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT event_id::text, client_event_id::text, schema_version, run_id, trial_id,
			seq_no, actor_id, actor_type, verb, object_data, result_data, context_data,
			sim_time_ms, occurred_at, ingested_at
		FROM evidence_events
		WHERE run_id = $1 AND seq_no > $2
		ORDER BY seq_no
		LIMIT $3`, runID, afterSeq, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	events := make([]dto.EvidenceEventResponse, 0)
	for rows.Next() {
		var event dto.EvidenceEventResponse
		var objectRaw, resultRaw, contextRaw []byte
		if err := rows.Scan(
			&event.EventID, &event.ClientEventID, &event.SchemaVersion, &event.RunID,
			&event.TrialID, &event.SeqNo, &event.ActorID, &event.ActorType, &event.Verb,
			&objectRaw, &resultRaw, &contextRaw, &event.SimTimeMs,
			&event.OccurredAt, &event.IngestedAt,
		); err != nil {
			return nil, err
		}
		if err := decodeEvidenceJSON(&event, objectRaw, resultRaw, contextRaw); err != nil {
			return nil, err
		}
		events = append(events, event)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return events, nil
}

type queryRower interface {
	QueryRowContext(context.Context, string, ...interface{}) *sql.Row
}

func getEvidenceByClientID(
	ctx context.Context,
	q queryRower,
	runID, actorID int64,
	clientEventID string,
) (*dto.EvidenceEventResponse, error) {
	var event dto.EvidenceEventResponse
	var objectRaw, resultRaw, contextRaw []byte
	err := q.QueryRowContext(ctx,
		`SELECT event_id::text, client_event_id::text, schema_version, run_id, trial_id,
			seq_no, actor_id, actor_type, verb, object_data, result_data, context_data,
			sim_time_ms, occurred_at, ingested_at
		FROM evidence_events
		WHERE run_id = $1 AND actor_id = $2 AND client_event_id = $3`,
		runID, actorID, clientEventID,
	).Scan(
		&event.EventID, &event.ClientEventID, &event.SchemaVersion, &event.RunID,
		&event.TrialID, &event.SeqNo, &event.ActorID, &event.ActorType, &event.Verb,
		&objectRaw, &resultRaw, &contextRaw, &event.SimTimeMs,
		&event.OccurredAt, &event.IngestedAt,
	)
	if err != nil {
		return nil, err
	}
	if err := decodeEvidenceJSON(&event, objectRaw, resultRaw, contextRaw); err != nil {
		return nil, err
	}
	return &event, nil
}

func decodeEvidenceJSON(
	event *dto.EvidenceEventResponse,
	objectRaw, resultRaw, contextRaw []byte,
) error {
	if err := json.Unmarshal(objectRaw, &event.Object); err != nil {
		return fmt.Errorf("decode evidence object: %w", err)
	}
	if err := json.Unmarshal(resultRaw, &event.Result); err != nil {
		return fmt.Errorf("decode evidence result: %w", err)
	}
	if err := json.Unmarshal(contextRaw, &event.Context); err != nil {
		return fmt.Errorf("decode evidence context: %w", err)
	}
	return nil
}

func nonNilMap(value map[string]interface{}) map[string]interface{} {
	if value == nil {
		return map[string]interface{}{}
	}
	return value
}

func nonNilStrings(value []string) []string {
	if value == nil {
		return []string{}
	}
	return value
}
