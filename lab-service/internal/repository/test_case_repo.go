package repository

import (
	"context"
	"database/sql"
	"fmt"

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
	var resp dto.TestCaseResponse
	err := r.db.QueryRowContext(ctx,
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
	query := `SELECT id, lab_id, name, order_index, is_sample, is_hidden, weight,
		COALESCE(input, ''), COALESCE(expected, ''), time_limit_ms, memory_limit_mb, COALESCE(explanation, ''), created_at
		FROM lab_test_cases WHERE lab_id = $1`
	if includeSampleOnly {
		// A case can be accidentally marked both sample and hidden by an author.
		// The learner-facing run endpoint must always prefer confidentiality.
		query += " AND is_sample = TRUE AND is_hidden = FALSE"
	}
	query += " ORDER BY order_index"

	rows, err := r.db.QueryContext(ctx, query, labID)
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
	var results []dto.TestCaseResponse
	for _, req := range reqs {
		resp, err := r.Create(ctx, labID, &req)
		if err != nil {
			return nil, err
		}
		results = append(results, *resp)
	}
	return results, nil
}

func (r *TestCaseRepository) Update(ctx context.Context, testCaseID int64, req *dto.UpdateTestCaseRequest) error {
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
