package repository

import (
	"context"
	"database/sql"

	"lab-service/internal/dto"
)

type SubmissionRepository struct{ db *sql.DB }

func NewSubmissionRepository(db *sql.DB) *SubmissionRepository {
	return &SubmissionRepository{db: db}
}

func (r *SubmissionRepository) Create(ctx context.Context, labID, userID int64, language, code, query, script string) (int64, error) {
	var id int64
	err := r.db.QueryRowContext(ctx,
		`INSERT INTO lab_submissions (lab_id, user_id, language, code, query, script_content, status)
		VALUES ($1, $2, $3, $4, $5, $6, 'PENDING')
		RETURNING id`,
		labID, userID, language, code, query, script,
	).Scan(&id)
	return id, err
}

func (r *SubmissionRepository) UpdateStatus(ctx context.Context, subID int64, status string, score float64, passedTests, totalTests, runtimeMs, memoryKB int, compilerOutput string) error {
	_, err := r.db.ExecContext(ctx,
		`UPDATE lab_submissions
		SET status = $1, score = $2, passed_tests = $3, total_tests = $4,
			runtime_ms = $5, memory_kb = $6, compiler_output = $7,
			graded_at = NOW()
		WHERE id = $8`,
		status, score, passedTests, totalTests, runtimeMs, memoryKB, compilerOutput, subID)
	return err
}

// MarkHPCSubmitted stores the scheduler ID but keeps the lab submission
// pending. A scheduler accepting a job is not evidence that the work passed.
func (r *SubmissionRepository) MarkHPCSubmitted(ctx context.Context, subID, jobID int64) error {
	_, err := r.db.ExecContext(ctx,
		`UPDATE lab_submissions SET status = 'PENDING', slurm_job_id = $1 WHERE id = $2`,
		jobID, subID)
	return err
}

func (r *SubmissionRepository) MarkHPCFailed(ctx context.Context, subID int64, message string) error {
	_, err := r.db.ExecContext(ctx,
		`UPDATE lab_submissions SET status = 'FAILED', compiler_output = $1, graded_at = NOW() WHERE id = $2`,
		message, subID)
	return err
}

func (r *SubmissionRepository) GetByID(ctx context.Context, subID int64) (*dto.SubmissionResponse, error) {
	var resp dto.SubmissionResponse
	var slurmJobID sql.NullInt64
	err := r.db.QueryRowContext(ctx,
		`SELECT id, lab_id, user_id, language, status, score, max_score,
			passed_tests, total_tests, runtime_ms, memory_kb, compiler_output,
			slurm_job_id, submitted_at, graded_at
		FROM lab_submissions WHERE id = $1`, subID,
	).Scan(&resp.ID, &resp.LabID, &resp.UserID, &resp.Language, &resp.Status,
		&resp.Score, &resp.MaxScore, &resp.PassedTests, &resp.TotalTests,
		&resp.RuntimeMs, &resp.MemoryKB, &resp.CompilerOutput,
		&slurmJobID, &resp.SubmittedAt, &resp.GradedAt)
	if slurmJobID.Valid {
		resp.SlurmJobID = &slurmJobID.Int64
	}
	return &resp, err
}

func (r *SubmissionRepository) ListByLabAndUser(ctx context.Context, labID, userID int64, limit, offset int) ([]dto.SubmissionResponse, int, error) {
	var total int
	r.db.QueryRowContext(ctx,
		"SELECT COUNT(*) FROM lab_submissions WHERE lab_id = $1 AND user_id = $2",
		labID, userID).Scan(&total)

	rows, err := r.db.QueryContext(ctx,
		`SELECT id, lab_id, user_id, language, status, score, max_score,
			passed_tests, total_tests, runtime_ms, memory_kb,
			slurm_job_id, submitted_at, graded_at
		FROM lab_submissions
		WHERE lab_id = $1 AND user_id = $2
		ORDER BY submitted_at DESC
		LIMIT $3 OFFSET $4`,
		labID, userID, limit, offset)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	var subs []dto.SubmissionResponse
	for rows.Next() {
		var s dto.SubmissionResponse
		var slurmJobID sql.NullInt64
		rows.Scan(&s.ID, &s.LabID, &s.UserID, &s.Language, &s.Status,
			&s.Score, &s.MaxScore, &s.PassedTests, &s.TotalTests,
			&s.RuntimeMs, &s.MemoryKB, &slurmJobID, &s.SubmittedAt, &s.GradedAt)
		if slurmJobID.Valid {
			s.SlurmJobID = &slurmJobID.Int64
		}
		subs = append(subs, s)
	}
	return subs, total, nil
}

// InsertTestResult stores a per-test-case result.
func (r *SubmissionRepository) InsertTestResult(ctx context.Context, submissionID, testCaseID int64, status, actualOutput string, runtimeMs, memoryKB int) error {
	_, err := r.db.ExecContext(ctx,
		`INSERT INTO submission_test_results (submission_id, test_case_id, status, actual_output, runtime_ms, memory_kb)
		VALUES ($1, $2, $3, $4, $5, $6)`,
		submissionID, testCaseID, status, actualOutput, runtimeMs, memoryKB)
	return err
}

func (r *SubmissionRepository) GetTestResults(ctx context.Context, submissionID int64) ([]dto.TestResultResponse, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT r.test_case_id, t.name, r.status, r.actual_output, r.runtime_ms, r.memory_kb, t.is_sample
		FROM submission_test_results r
		JOIN lab_test_cases t ON t.id = r.test_case_id
		WHERE r.submission_id = $1
		ORDER BY t.order_index`, submissionID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var results []dto.TestResultResponse
	for rows.Next() {
		var r dto.TestResultResponse
		rows.Scan(&r.TestCaseID, &r.TestName, &r.Status, &r.ActualOutput,
			&r.RuntimeMs, &r.MemoryKB, &r.IsSample)
		results = append(results, r)
	}
	return results, nil
}

// CountByLabAndUser returns total submissions for quota checking.
func (r *SubmissionRepository) CountByLabAndUser(ctx context.Context, labID, userID int64) (int, error) {
	var count int
	err := r.db.QueryRowContext(ctx,
		"SELECT COUNT(*) FROM lab_submissions WHERE lab_id = $1 AND user_id = $2",
		labID, userID).Scan(&count)
	return count, err
}
