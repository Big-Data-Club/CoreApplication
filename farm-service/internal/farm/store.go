package farm

import (
	"context"
	_ "embed"
	"encoding/json"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed schema.sql
var schema string

type Store struct {
	Pool   *pgxpool.Pool
	Secret string
}

func (s *Store) Migrate(ctx context.Context) error {
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err = tx.Exec(ctx, "SELECT pg_advisory_xact_lock(734620118)"); err != nil {
		return err
	}
	if _, err = tx.Exec(ctx, schema); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

type View struct {
	State         State     `json:"state"`
	Catalog       []Species `json:"catalog"`
	ServerTime    time.Time `json:"server_time"`
	PendingEvents int       `json:"pending_events"`
	DailyLimit    int       `json:"daily_limit"`
	Reward        int       `json:"reward"`
}

// Every mutation locks a single farm, so multiple tabs/replicas cannot double harvest.
func (s *Store) transact(ctx context.Context, user int64, change func(*State, time.Time, pgx.Tx) error) (View, error) {
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return View{}, err
	}
	defer tx.Rollback(ctx)
	initial, _ := json.Marshal(NewState())
	if _, err = tx.Exec(ctx, "INSERT INTO farm_states(user_id,state) VALUES($1,$2) ON CONFLICT DO NOTHING", user, initial); err != nil {
		return View{}, err
	}
	var raw []byte
	var now time.Time
	if err = tx.QueryRow(ctx, "SELECT state,clock_timestamp() FROM farm_states WHERE user_id=$1 FOR UPDATE", user).Scan(&raw, &now); err != nil {
		return View{}, err
	}
	var state State
	if err = json.Unmarshal(raw, &state); err != nil {
		return View{}, err
	}
	state.Day(now)
	if change != nil {
		if err = change(&state, now, tx); err != nil {
			return View{}, err
		}
	}
	if change != nil {
		raw, err = json.Marshal(state)
		if err != nil {
			return View{}, err
		}
		if _, err = tx.Exec(ctx, "UPDATE farm_states SET state=$2,updated_at=$3 WHERE user_id=$1", user, raw, now); err != nil {
			return View{}, err
		}
	}
	var pending int
	if err = tx.QueryRow(ctx, "SELECT count(*) FROM farm_outbox WHERE user_id=$1 AND published_at IS NULL", user).Scan(&pending); err != nil {
		return View{}, err
	}
	if err = tx.Commit(ctx); err != nil {
		return View{}, err
	}
	return View{State: state.PublicState(), Catalog: Catalog, ServerTime: now, PendingEvents: pending, DailyLimit: DailyLimit, Reward: Reward}, nil
}
func (s *Store) Get(ctx context.Context, user int64) (View, error) { return s.transact(ctx, user, nil) }
func (s *Store) Care(ctx context.Context, user int64, plot int) (View, error) {
	return s.transact(ctx, user, func(state *State, now time.Time, _ pgx.Tx) error { return state.Care(plot, now) })
}
func (s *Store) Start(ctx context.Context, user int64, plot int, kind string) (View, error) {
	return s.transact(ctx, user, func(state *State, now time.Time, _ pgx.Tx) error { _, err := state.Start(plot, kind, now); return err })
}
func (s *Store) Answer(ctx context.Context, user int64, plot int, id, answer string) (Result, error) {
	var result Result
	_, err := s.transact(ctx, user, func(state *State, now time.Time, tx pgx.Tx) error {
		var raw []byte
		err := tx.QueryRow(ctx, "SELECT result FROM farm_answers WHERE challenge_id=$1 AND user_id=$2", id, user).Scan(&raw)
		if err == nil {
			return json.Unmarshal(raw, &result)
		}
		if !errors.Is(err, pgx.ErrNoRows) {
			return err
		}
		var event *Event
		result, event, err = state.Answer(user, plot, id, answer, now, s.Secret)
		if err != nil {
			return err
		}
		raw, err = json.Marshal(result)
		if err != nil {
			return err
		}
		if _, err = tx.Exec(ctx, "INSERT INTO farm_answers(challenge_id,user_id,result) VALUES($1,$2,$3)", id, user, raw); err != nil {
			return err
		}
		if event != nil {
			payload, err := json.Marshal(event)
			if err != nil {
				return err
			}
			_, err = tx.Exec(ctx, "INSERT INTO farm_outbox(event_id,user_id,payload) VALUES($1,$2,$3)", event.EventID, user, payload)
			return err
		}
		return nil
	})
	return result, err
}

// Dispatch holds the row lock until broker acknowledgement. Crash after publish
// replays the same event ID; Auth's inbox makes this safe. Never mark on failure.
func (s *Store) Dispatch(ctx context.Context, publish func(context.Context, int64, []byte) error) (bool, error) {
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return false, err
	}
	defer tx.Rollback(ctx)
	var id string
	var user int64
	var payload []byte
	err = tx.QueryRow(ctx, "SELECT event_id,user_id,payload FROM farm_outbox WHERE published_at IS NULL ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1").Scan(&id, &user, &payload)
	if errors.Is(err, pgx.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if err = publish(ctx, user, payload); err != nil {
		return false, err
	}
	if _, err = tx.Exec(ctx, "UPDATE farm_outbox SET published_at=now() WHERE event_id=$1", id); err != nil {
		return false, err
	}
	return true, tx.Commit(ctx)
}
