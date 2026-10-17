package repository

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// LearningOutbox claims one attempt with a short database statement. The HTTP
// call to LMS must happen after Claim returns, without a connection or row lock.
type LearningOutbox struct{ Pool *pgxpool.Pool }

type LearningAttempt struct {
	ChallengeID string
	Payload     []byte
}

func (r LearningOutbox) Claim(ctx context.Context) (LearningAttempt, bool, error) {
	var attempt LearningAttempt
	err := r.Pool.QueryRow(ctx, `WITH pending AS (
		SELECT challenge_id FROM game_learning_outbox
		WHERE delivered_at IS NULL AND next_attempt_at <= now()
		ORDER BY next_attempt_at, created_at LIMIT 1 FOR UPDATE SKIP LOCKED
	)
	UPDATE game_learning_outbox AS outbox
	SET next_attempt_at = now() + interval '30 seconds', attempts = attempts + 1
	FROM pending WHERE outbox.challenge_id = pending.challenge_id
	RETURNING outbox.challenge_id::text, outbox.payload`).Scan(&attempt.ChallengeID, &attempt.Payload)
	if errors.Is(err, pgx.ErrNoRows) {
		return attempt, false, nil
	}
	return attempt, err == nil, err
}

func (r LearningOutbox) Delivered(ctx context.Context, challengeID string) error {
	_, err := r.Pool.Exec(ctx, `UPDATE game_learning_outbox SET delivered_at = now() WHERE challenge_id = $1 AND delivered_at IS NULL`, challengeID)
	return err
}

func (r LearningOutbox) Retry(ctx context.Context, challengeID string) error {
	_, err := r.Pool.Exec(ctx, `UPDATE game_learning_outbox
		SET next_attempt_at = now() + LEAST(60, 5 * attempts) * interval '1 second'
		WHERE challenge_id = $1 AND delivered_at IS NULL`, challengeID)
	return err
}
