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
	"bdc/farm-service/internal/game/repository"
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

// DispatchLearning releases its database connection before calling LMS. A
// claimed row becomes available again after the lease if a worker dies, and
// LMS de-duplicates any replay by challenge UUID.
func DispatchLearning(ctx context.Context, pool *pgxpool.Pool, client *LMSClient) (bool, error) {
	outbox := repository.LearningOutbox{Pool: pool}
	attempt, claimed, err := outbox.Claim(ctx)
	if err != nil {
		return false, err
	}
	if !claimed {
		return false, nil
	}
	if err = client.deliver(ctx, attempt.Payload); err != nil {
		cleanup, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		_ = outbox.Retry(cleanup, attempt.ChallengeID)
		cancel()
		return true, err
	}
	cleanup, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	return true, outbox.Delivered(cleanup, attempt.ChallengeID)
}
