package repository

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"slices"

	"lab-service/internal/dto"
)

type TestCaseRepository struct{ db *sql.DB }

func NewTestCaseRepository(db *sql.DB) *TestCaseRepository {
	return &TestCaseRepository{db: db}
}

func (r *TestCaseRepository) CountPublicSamples(ctx context.Context, labID int64) (int, error) {
	var count int
	err := r.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM lab_test_cases WHERE lab_id=$1 AND is_sample=TRUE AND is_hidden=FALSE`, labID).Scan(&count)
	return count, err
}

func (r *TestCaseRepository) Create(ctx context.Context, labID int64, req *dto.CreateTestCaseRequest) (*dto.TestCaseResponse, error) {
	results, err := r.BulkCreate(ctx, labID, []dto.CreateTestCaseRequest{*req})
	if err != nil {
		return nil, err
	}
	return &results[0], nil
}

type caseQuerier interface {
	QueryRowContext(context.Context, string, ...interface{}) *sql.Row
	QueryContext(context.Context, string, ...interface{}) (*sql.Rows, error)
}

func insertTestCase(ctx context.Context, q caseQuerier, labID int64, req *dto.CreateTestCaseRequest) (*dto.TestCaseResponse, error) {
	var resp dto.TestCaseResponse
	err := q.QueryRowContext(ctx,
		`INSERT INTO lab_test_cases (lab_id, name, order_index, is_sample, is_hidden, weight,
			input, expected, time_limit_ms, memory_limit_mb, explanation)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
		RETURNING id, lab_id, name, order_index, is_sample, is_hidden, weight,
			input, expected, time_limit_ms, memory_limit_mb, explanation, created_at`,
		labID, req.Name, req.OrderIndex, req.IsSample, req.IsHidden, req.Weight,
		req.Input, req.Expected, req.TimeLimitMs, req.MemoryLimitMB, req.Explanation,
	).Scan(&resp.ID, &resp.LabID, &resp.Name, &resp.OrderIndex, &resp.IsSample,
		&resp.IsHidden, &resp.Weight, &resp.Input, &resp.Expected,
		&resp.TimeLimitMs, &resp.MemoryLimitMB, &resp.Explanation, &resp.CreatedAt)
	return &resp, err
}

func (r *TestCaseRepository) ListByLab(ctx context.Context, labID int64, includeSampleOnly bool) ([]dto.TestCaseResponse, error) {
	return listTestCases(ctx, r.db, labID, includeSampleOnly)
}
func listTestCases(ctx context.Context, q caseQuerier, labID int64, includeSampleOnly bool) ([]dto.TestCaseResponse, error) {
	query := `SELECT id, lab_id, name, order_index, is_sample, is_hidden, weight,
		COALESCE(input, ''), COALESCE(expected, ''), time_limit_ms, memory_limit_mb, COALESCE(explanation, ''), created_at
		FROM lab_test_cases WHERE lab_id = $1`
	if includeSampleOnly {
		// A case can be accidentally marked both sample and hidden by an author.
		// The learner-facing run endpoint must always prefer confidentiality.
		query += " AND is_sample = TRUE AND is_hidden = FALSE"
	}
	query += " ORDER BY order_index, id"

	rows, err := q.QueryContext(ctx, query, labID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	cases := make([]dto.TestCaseResponse, 0)
	for rows.Next() {
		var c dto.TestCaseResponse
		if err := rows.Scan(&c.ID, &c.LabID, &c.Name, &c.OrderIndex, &c.IsSample,
			&c.IsHidden, &c.Weight, &c.Input, &c.Expected,
			&c.TimeLimitMs, &c.MemoryLimitMB, &c.Explanation, &c.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan test case: %w", err)
		}
		cases = append(cases, c)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return cases, nil
}

func (r *TestCaseRepository) Delete(ctx context.Context, testCaseID int64) error {
	_, err := r.db.ExecContext(ctx, "DELETE FROM lab_test_cases WHERE id = $1", testCaseID)
	return err
}

func (r *TestCaseRepository) BulkCreate(ctx context.Context, labID int64, reqs []dto.CreateTestCaseRequest) ([]dto.TestCaseResponse, error) {
	return r.writeSuite(ctx, labID, reqs, nil, "", false)
}
func (r *TestCaseRepository) Replace(ctx context.Context, labID int64, req dto.ReplaceTestCasesRequest) ([]dto.TestCaseResponse, error) {
	return r.writeSuite(ctx, labID, req.TestCases, req.ExpectedIDs, req.ExpectedRevision, true)
}
func (r *TestCaseRepository) writeSuite(ctx context.Context, labID int64, reqs []dto.CreateTestCaseRequest, expectedIDs []int64, expectedRevision string, replace bool) ([]dto.TestCaseResponse, error) {
	if err := dto.ValidateTestCases(reqs); err != nil {
		return nil, err
	}
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback()
	var lockedID int64
	if err = tx.QueryRowContext(ctx, "SELECT id FROM labs WHERE id=$1 FOR UPDATE", labID).Scan(&lockedID); err != nil {
		return nil, err
	}
	rows, err := tx.QueryContext(ctx, "SELECT id FROM lab_test_cases WHERE lab_id=$1 ORDER BY id FOR UPDATE", labID)
	if err != nil {
		return nil, err
	}
	ids := []int64{}
	for rows.Next() {
		var id int64
		if err = rows.Scan(&id); err != nil {
			rows.Close()
			return nil, err
		}
		ids = append(ids, id)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return nil, err
	}
	current := []dto.TestCaseResponse{}
	if replace {
		current, err = listTestCases(ctx, tx, labID, false)
		if err != nil {
			return nil, err
		}
		if expectedRevision != "" && SuiteRevision(current) != expectedRevision {
			return nil, fmt.Errorf("test suite changed; reload before applying this draft")
		}
		snapshot := append([]int64{}, expectedIDs...)
		slices.Sort(snapshot)
		if !slices.Equal(ids, snapshot) {
			return nil, fmt.Errorf("test suite changed; reload before applying this draft")
		}
		for _, old := range current[min(len(reqs), len(current)):] {
			if _, err = tx.ExecContext(ctx, "DELETE FROM lab_test_cases WHERE id=$1 AND lab_id=$2", old.ID, labID); err != nil {
				return nil, fmt.Errorf("cannot remove a testcase referenced by submissions; retain existing cases and append new ones")
			}
		}
	} else if len(ids)+len(reqs) > 50 {
		return nil, fmt.Errorf("a lab supports at most 50 test cases")
	}
	results := make([]dto.TestCaseResponse, 0, len(reqs))
	for index, req := range reqs {
		var resp *dto.TestCaseResponse
		var err error
		if replace && index < len(current) {
			resp, err = updateFullTestCase(ctx, tx, labID, current[index].ID, &req)
		} else {
			resp, err = insertTestCase(ctx, tx, labID, &req)
		}
		if err != nil {
			return nil, err
		}
		results = append(results, *resp)
	}
	if err = tx.Commit(); err != nil {
		return nil, err
	}
	return results, nil
}
func (r *TestCaseRepository) LabID(ctx context.Context, id int64) (int64, error) {
	var labID int64
	err := r.db.QueryRowContext(ctx, "SELECT lab_id FROM lab_test_cases WHERE id=$1", id).Scan(&labID)
	return labID, err
}

func (r *TestCaseRepository) Update(ctx context.Context, testCaseID int64, req *dto.UpdateTestCaseRequest) error {
	check := dto.CreateTestCaseRequest{Weight: 1}
	if req.Input != nil {
		check.Input = *req.Input
	}
	if req.Expected != nil {
		check.Expected = *req.Expected
	}
	if req.Name != nil {
		check.Name = *req.Name
	}
	if req.Weight != nil {
		check.Weight = *req.Weight
	}
	if req.OrderIndex != nil {
		check.OrderIndex = *req.OrderIndex
	}
	if req.Explanation != nil {
		check.Explanation = *req.Explanation
	}
	check.TimeLimitMs = req.TimeLimitMs
	check.MemoryLimitMB = req.MemoryLimitMB
	if req.IsSample != nil {
		check.IsSample = *req.IsSample
	}
	if req.IsHidden != nil {
		check.IsHidden = *req.IsHidden
	}
	if err := dto.ValidateTestCases([]dto.CreateTestCaseRequest{check}); err != nil {
		return err
	}

	query := "UPDATE lab_test_cases SET "
	var args []interface{}
	argID := 1
	first := true

	updateField := func(field string, val interface{}) {
		if !first {
			query += ", "
		}
		first = false
		query += fmt.Sprintf("%s = $%d", field, argID)
		args = append(args, val)
		argID++
	}

	if req.Name != nil {
		updateField("name", *req.Name)
	}
	if req.OrderIndex != nil {
		updateField("order_index", *req.OrderIndex)
	}
	if req.IsSample != nil {
		updateField("is_sample", *req.IsSample)
	}
	if req.IsHidden != nil {
		updateField("is_hidden", *req.IsHidden)
	}
	if req.Weight != nil {
		updateField("weight", *req.Weight)
	}
	if req.Input != nil {
		updateField("input", *req.Input)
	}
	if req.Expected != nil {
		updateField("expected", *req.Expected)
	}
	if req.TimeLimitMs != nil {
		updateField("time_limit_ms", req.TimeLimitMs)
	}
	if req.MemoryLimitMB != nil {
		updateField("memory_limit_mb", req.MemoryLimitMB)
	}
	if req.Explanation != nil {
		updateField("explanation", *req.Explanation)
	}

	if first {
		return nil
	}

	query += fmt.Sprintf(" WHERE id = $%d", argID)
	args = append(args, testCaseID)

	_, err := r.db.ExecContext(ctx, query, args...)
	return err
}

// A change token includes inputs, outputs, visibility and weights, not just IDs.
func SuiteRevision(cases []dto.TestCaseResponse) string {
	raw, _ := json.Marshal(cases)
	hash := sha256.Sum256(raw)
	return hex.EncodeToString(hash[:])
}

func updateFullTestCase(ctx context.Context, q caseQuerier, labID, id int64, req *dto.CreateTestCaseRequest) (*dto.TestCaseResponse, error) {
	var resp dto.TestCaseResponse
	err := q.QueryRowContext(ctx, `UPDATE lab_test_cases SET name=$1,order_index=$2,is_sample=$3,is_hidden=$4,weight=$5,input=$6,expected=$7,time_limit_ms=$8,memory_limit_mb=$9,explanation=$10 WHERE id=$11 AND lab_id=$12 RETURNING id,lab_id,name,order_index,is_sample,is_hidden,weight,input,expected,time_limit_ms,memory_limit_mb,explanation,created_at`, req.Name, req.OrderIndex, req.IsSample, req.IsHidden, req.Weight, req.Input, req.Expected, req.TimeLimitMs, req.MemoryLimitMB, req.Explanation, id, labID).Scan(&resp.ID, &resp.LabID, &resp.Name, &resp.OrderIndex, &resp.IsSample, &resp.IsHidden, &resp.Weight, &resp.Input, &resp.Expected, &resp.TimeLimitMs, &resp.MemoryLimitMB, &resp.Explanation, &resp.CreatedAt)
	return &resp, err
}
