package repository

import (
	"context"
	"database/sql"

	"lab-service/internal/dto"
)

type TestCaseRepository struct{ db *sql.DB }

func NewTestCaseRepository(db *sql.DB) *TestCaseRepository {
	return &TestCaseRepository{db: db}
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
		input, expected, time_limit_ms, memory_limit_mb, explanation, created_at
		FROM lab_test_cases WHERE lab_id = $1`
	if includeSampleOnly {
		query += " AND is_sample = TRUE"
	}
	query += " ORDER BY order_index"

	rows, err := r.db.QueryContext(ctx, query, labID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var cases []dto.TestCaseResponse
	for rows.Next() {
		var c dto.TestCaseResponse
		rows.Scan(&c.ID, &c.LabID, &c.Name, &c.OrderIndex, &c.IsSample,
			&c.IsHidden, &c.Weight, &c.Input, &c.Expected,
			&c.TimeLimitMs, &c.MemoryLimitMB, &c.Explanation, &c.CreatedAt)
		cases = append(cases, c)
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
