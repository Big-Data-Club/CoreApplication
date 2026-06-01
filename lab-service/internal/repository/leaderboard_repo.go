package repository

import (
	"context"
	"database/sql"
	"time"
)

type LeaderboardRepository struct{ db *sql.DB }

func NewLeaderboardRepository(db *sql.DB) *LeaderboardRepository {
	return &LeaderboardRepository{db: db}
}

type LeaderboardEntry struct {
	Rank              int       `json:"rank"`
	UserID            int64     `json:"user_id"`
	FullName          string    `json:"full_name"`
	Email             string    `json:"email"`
	BestScore         float64   `json:"best_score"`
	BestRuntimeMs     int       `json:"best_runtime_ms"`
	BestMemoryKB      int       `json:"best_memory_kb"`
	AttemptCount      int       `json:"attempt_count"`
	FirstAcceptedAt   *time.Time `json:"first_accepted_at,omitempty"`
}

func (r *LeaderboardRepository) UpsertEntry(ctx context.Context, labID, userID, submissionID int64, score float64, runtimeMs, memoryKB int) error {
	now := time.Now()
	_, err := r.db.ExecContext(ctx,
		`INSERT INTO lab_leaderboard (lab_id, user_id, best_submission_id, best_score, best_runtime_ms, best_memory_kb, attempt_count, first_accepted_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, 1, $7, $7)
		ON CONFLICT (lab_id, user_id) DO UPDATE SET
			best_submission_id = CASE WHEN EXCLUDED.best_score > lab_leaderboard.best_score
				OR (EXCLUDED.best_score = lab_leaderboard.best_score AND EXCLUDED.best_runtime_ms < lab_leaderboard.best_runtime_ms)
				THEN EXCLUDED.best_submission_id ELSE lab_leaderboard.best_submission_id END,
			best_score = GREATEST(lab_leaderboard.best_score, EXCLUDED.best_score),
			best_runtime_ms = CASE WHEN EXCLUDED.best_score > lab_leaderboard.best_score
				OR (EXCLUDED.best_score = lab_leaderboard.best_score AND EXCLUDED.best_runtime_ms < lab_leaderboard.best_runtime_ms)
				THEN EXCLUDED.best_runtime_ms ELSE lab_leaderboard.best_runtime_ms END,
			best_memory_kb = CASE WHEN EXCLUDED.best_score > lab_leaderboard.best_score
				OR (EXCLUDED.best_score = lab_leaderboard.best_score AND EXCLUDED.best_runtime_ms < lab_leaderboard.best_runtime_ms)
				THEN EXCLUDED.best_memory_kb ELSE lab_leaderboard.best_memory_kb END,
			attempt_count = lab_leaderboard.attempt_count + 1,
			first_accepted_at = COALESCE(lab_leaderboard.first_accepted_at, EXCLUDED.first_accepted_at),
			updated_at = EXCLUDED.updated_at`,
		labID, userID, submissionID, score, runtimeMs, memoryKB, now)
	return err
}

func (r *LeaderboardRepository) GetLabLeaderboard(ctx context.Context, labID int64, sortBy string, limit, offset int) ([]LeaderboardEntry, int, error) {
	orderBy := "best_score DESC, best_runtime_ms ASC"
	switch sortBy {
	case "runtime":
		orderBy = "best_runtime_ms ASC, best_score DESC"
	case "memory":
		orderBy = "best_memory_kb ASC, best_score DESC"
	case "attempts":
		orderBy = "attempt_count ASC, best_score DESC"
	}

	var total int
	r.db.QueryRowContext(ctx,
		"SELECT COUNT(*) FROM lab_leaderboard WHERE lab_id = $1", labID).Scan(&total)

	query := `SELECT lb.user_id, u.full_name, u.email,
			lb.best_score, lb.best_runtime_ms, lb.best_memory_kb,
			lb.attempt_count, lb.first_accepted_at
		FROM lab_leaderboard lb
		JOIN users u ON u.id = lb.user_id
		WHERE lb.lab_id = $1
		ORDER BY ` + orderBy + `
		LIMIT $2 OFFSET $3`

	rows, err := r.db.QueryContext(ctx, query, labID, limit, offset)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	var entries []LeaderboardEntry
	rank := offset + 1
	for rows.Next() {
		var e LeaderboardEntry
		rows.Scan(&e.UserID, &e.FullName, &e.Email,
			&e.BestScore, &e.BestRuntimeMs, &e.BestMemoryKB,
			&e.AttemptCount, &e.FirstAcceptedAt)
		e.Rank = rank
		rank++
		entries = append(entries, e)
	}
	return entries, total, nil
}
