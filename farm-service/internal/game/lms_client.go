package game

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"bdc/farm-service/internal/farm"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type LMSClient struct {
	Base, Secret string
	HTTP         *http.Client
}

var ErrNoLMSQuestion = errors.New("no eligible LMS question")

func NewLMSClient(base, secret string) *LMSClient {
	return &LMSClient{Base: strings.TrimRight(base, "/"), Secret: secret, HTTP: &http.Client{Timeout: 4 * time.Second}}
}
func (c *LMSClient) Question(ctx context.Context, user int64, kind, exclude string) (farm.Question, error) {
	var q farm.Question
	query := url.Values{"user_id": {strconv.FormatInt(user, 10)}, "kind": {kind}}
	if exclude != "" {
		query.Set("exclude", exclude)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.Base+"/api/v1/internal/farm/question?"+query.Encode(), nil)
	if err != nil {
		return q, err
	}
	req.Header.Set("X-API-Secret", c.Secret)
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return q, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return q, ErrNoLMSQuestion
	}
	if resp.StatusCode != http.StatusOK {
		return q, fmt.Errorf("LMS question status %d", resp.StatusCode)
	}
	err = json.NewDecoder(io.LimitReader(resp.Body, 8192)).Decode(&q)
	return q, err
}
func (c *LMSClient) deliver(ctx context.Context, payload []byte) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.Base+"/api/v1/internal/farm/attempt", bytes.NewReader(payload))
	if err != nil {
		return err
	}
	req.Header.Set("X-API-Secret", c.Secret)
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNoContent {
		return fmt.Errorf("LMS attempt status %d", resp.StatusCode)
	}
	return nil
}

// DispatchLearning keeps the row locked across delivery. A failed request
// remains pending; LMS de-duplicates successful retries by challenge UUID.
func DispatchLearning(ctx context.Context, pool *pgxpool.Pool, client *LMSClient) (bool, error) {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return false, err
	}
	defer tx.Rollback(ctx)
	var id string
	var payload []byte
	err = tx.QueryRow(ctx, `SELECT challenge_id::text,payload FROM game_learning_outbox
		WHERE delivered_at IS NULL AND next_attempt_at<=now() ORDER BY next_attempt_at,created_at LIMIT 1 FOR UPDATE SKIP LOCKED`).Scan(&id, &payload)
	if err == pgx.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if err = client.deliver(ctx, payload); err != nil {
		_, _ = tx.Exec(ctx, `UPDATE game_learning_outbox SET attempts=attempts+1,next_attempt_at=now()+LEAST(60,5*(attempts+1))*interval '1 second' WHERE challenge_id=$1`, id)
		_ = tx.Commit(ctx)
		return true, err
	}
	if _, err = tx.Exec(ctx, `UPDATE game_learning_outbox SET delivered_at=now(),attempts=attempts+1 WHERE challenge_id=$1`, id); err != nil {
		return true, err
	}
	return true, tx.Commit(ctx)
}
