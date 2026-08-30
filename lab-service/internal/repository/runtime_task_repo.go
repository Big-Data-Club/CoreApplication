package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"

	"lab-service/internal/dto"
)

type RuntimeTask struct {
	dto.RuntimeTaskResponse
	RuntimeType    string
	VerifierConfig map[string]interface{}
}
type RuntimeTaskRepository struct{ db *sql.DB }

func NewRuntimeTaskRepository(db *sql.DB) *RuntimeTaskRepository {
	return &RuntimeTaskRepository{db: db}
}

func (r *RuntimeTaskRepository) Create(ctx context.Context, labID int64, runtimeType string, req dto.CreateRuntimeTaskRequest) (*dto.RuntimeTaskResponse, error) {
	config, err := json.Marshal(req.VerifierConfig)
	if err != nil {
		return nil, fmt.Errorf("invalid verifier config: %w", err)
	}
	var out dto.RuntimeTaskResponse
	err = r.db.QueryRowContext(ctx, `INSERT INTO lab_runtime_tasks(lab_id,title,description,runtime_type,verifier_type,verifier_config,weight,is_required,order_index) VALUES($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9) RETURNING id,lab_id,title,description,verifier_type,weight,is_required,order_index`, labID, req.Title, req.Description, runtimeType, req.VerifierType, string(config), req.Weight, req.IsRequired, req.OrderIndex).Scan(&out.ID, &out.LabID, &out.Title, &out.Description, &out.VerifierType, &out.Weight, &out.IsRequired, &out.OrderIndex)
	return &out, err
}

func (r *RuntimeTaskRepository) List(ctx context.Context, labID, userID int64, includeVerifier bool) ([]RuntimeTask, error) {
	rows, err := r.db.QueryContext(ctx, `SELECT t.id,t.lab_id,t.title,t.description,t.runtime_type,t.verifier_type,t.verifier_config,t.weight,t.is_required,t.order_index,COALESCE(a.passed,false),COALESCE(a.message,'') FROM lab_runtime_tasks t LEFT JOIN LATERAL(SELECT passed,message FROM lab_runtime_task_attempts WHERE task_id=t.id AND user_id=$2 ORDER BY checked_at DESC LIMIT 1)a ON true WHERE t.lab_id=$1 ORDER BY t.order_index,t.id`, labID, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []RuntimeTask{}
	for rows.Next() {
		var t RuntimeTask
		var raw []byte
		if err := rows.Scan(&t.ID, &t.LabID, &t.Title, &t.Description, &t.RuntimeType, &t.VerifierType, &raw, &t.Weight, &t.IsRequired, &t.OrderIndex, &t.Passed, &t.LastMessage); err != nil {
			return nil, err
		}
		if includeVerifier {
			if err := json.Unmarshal(raw, &t.VerifierConfig); err != nil {
				return nil, fmt.Errorf("invalid verifier config for task %d: %w", t.ID, err)
			}
		}
		out = append(out, t)
	}
	return out, rows.Err()
}

func (r *RuntimeTaskRepository) Delete(ctx context.Context, taskID int64) error {
	res, err := r.db.ExecContext(ctx, `DELETE FROM lab_runtime_tasks WHERE id=$1`, taskID)
	if err != nil {
		return err
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return fmt.Errorf("task not found")
	}
	return nil
}
func (r *RuntimeTaskRepository) SaveAttempt(ctx context.Context, t RuntimeTask, userID int64, session string, passed bool, message string, evidence map[string]interface{}) error {
	raw, err := json.Marshal(evidence)
	if err != nil {
		return err
	}
	_, err = r.db.ExecContext(ctx, `INSERT INTO lab_runtime_task_attempts(task_id,lab_id,user_id,session_id,passed,message,evidence)VALUES($1,$2,$3,$4,$5,$6,$7::jsonb)`, t.ID, t.LabID, userID, session, passed, message, string(raw))
	return err
}
func (r *RuntimeTaskRepository) LatestHPCStatus(ctx context.Context, labID, userID int64) (string, bool, error) {
	var status string
	var job sql.NullInt64
	err := r.db.QueryRowContext(ctx, `SELECT status,slurm_job_id FROM lab_submissions WHERE lab_id=$1 AND user_id=$2 ORDER BY submitted_at DESC LIMIT 1`, labID, userID).Scan(&status, &job)
	if err == sql.ErrNoRows {
		return "", false, nil
	}
	return status, job.Valid, err
}
