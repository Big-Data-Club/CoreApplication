package farm

import (
	"context"
	"encoding/json"
	"errors"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func testStore(t *testing.T) *Store {
	t.Helper()
	url := os.Getenv("FARM_TEST_DATABASE_URL")
	if url == "" {
		t.Skip("set FARM_TEST_DATABASE_URL to a disposable PostgreSQL database")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	store := &Store{Pool: pool, Secret: "farm-contract-test-secret-32-bytes"}
	if err = store.Migrate(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err = pool.Exec(ctx, "TRUNCATE farm_states, farm_answers, farm_outbox"); err != nil {
		t.Fatal(err)
	}
	return store
}
func TestPostgresConcurrentHarvestAndOutbox(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	_, err := s.transact(ctx, 41, func(state *State, now time.Time, _ pgx.Tx) error {
		past := now.Add(-time.Minute)
		state.Plots[0].ReadyAt = &past
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	view, err := s.Start(ctx, 41, 1, "quiz")
	if err != nil {
		t.Fatal(err)
	}
	id := view.State.Plots[0].Challenge.ID
	var raw []byte
	if err = s.Pool.QueryRow(ctx, "SELECT state FROM farm_states WHERE user_id=41").Scan(&raw); err != nil {
		t.Fatal(err)
	}
	var state State
	_ = json.Unmarshal(raw, &state)
	answer := state.Plots[0].Challenge.Question.Answer
	if _, err = s.Answer(ctx, 42, 1, id, answer); err == nil {
		t.Fatal("cross-user challenge accepted")
	}
	var wg sync.WaitGroup
	errs := make(chan error, 20)
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			result, err := s.Answer(ctx, 41, 1, id, answer)
			if err != nil {
				errs <- err
			} else if result.Awarded != 5 {
				errs <- errors.New("replay result differs")
			}
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Error(err)
	}
	view, err = s.Get(ctx, 41)
	if err != nil {
		t.Fatal(err)
	}
	if view.State.Earned != 5 || view.State.Plots[0].Harvests != 1 || view.PendingEvents != 1 {
		t.Fatalf("duplicate harvest: %+v", view)
	}
	_, err = s.Dispatch(ctx, func(context.Context, int64, []byte) error { return errors.New("broker unavailable") })
	if err == nil {
		t.Fatal("broker error swallowed")
	}
	view, _ = s.Get(ctx, 41)
	if view.PendingEvents != 1 {
		t.Fatal("lost event during outage")
	}
	var event Event
	sent, err := s.Dispatch(ctx, func(_ context.Context, user int64, data []byte) error {
		if user != 41 {
			t.Error("wrong partition key")
		}
		return json.Unmarshal(data, &event)
	})
	if err != nil || !sent || event.EventID != id {
		t.Fatal("dispatch failed")
	}
	view, _ = s.Get(ctx, 41)
	if view.PendingEvents != 0 {
		t.Fatal("publish not marked")
	}
	// Simulate crash after broker ack but before marking: replay retains exact identity.
	_, err = s.Pool.Exec(ctx, "UPDATE farm_outbox SET published_at=NULL")
	if err != nil {
		t.Fatal(err)
	}
	_, err = s.Dispatch(ctx, func(_ context.Context, _ int64, data []byte) error {
		var e Event
		_ = json.Unmarshal(data, &e)
		if e.EventID != id {
			t.Error("replay minted new ID")
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
}
func TestHTTPAuthorizationAndValidation(t *testing.T) {
	s := testStore(t)
	secret := strings.Repeat("s", 32)
	handler := Handler(s, secret)
	claims := Claims{UserID: 41, Roles: []string{"ROLE_USER"}, RegisteredClaims: jwt.RegisteredClaims{ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour))}}
	token, _ := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(secret))
	for _, tc := range []struct {
		method, path, body, token string
		status                    int
	}{
		{"GET", "/api/v1/farm", "", "", 401},
		{"GET", "/api/v1/farm", "", token, 200},
		{"POST", "/api/v1/farm/plots/7/care", "{}", token, 404},
		{"POST", "/api/v1/farm/plots/1/care", `{"user_id":42}`, token, 400},
		{"POST", "/api/v1/farm/plots/1/care", `{} {}`, token, 400},
		{"POST", "/api/v1/farm/plots/1/challenge", `{"kind":"quiz"}`, token, 409},
		{"POST", "/api/v1/farm/plots/1/answer", `{"challenge_id":"bad","answer":"1"}`, token, 400},
		{"POST", "/api/v1/farm/plots/1/care", `{}`, token, 200},
	} {
		r := httptest.NewRequest(tc.method, tc.path, strings.NewReader(tc.body))
		if tc.token != "" {
			r.Header.Set("Authorization", "Bearer "+tc.token)
		}
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		if w.Code != tc.status {
			t.Errorf("%s %s: %d != %d", tc.method, tc.path, w.Code, tc.status)
		}
	}
}
