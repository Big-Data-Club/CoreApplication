package runtime

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"fmt"
	"net/url"
	"strings"
	"time"

	"github.com/lib/pq"
)

// Practice runs on a dedicated PostgreSQL instance. A fresh login can SELECT
// only its fixture tables; learner SQL never receives an application DB role.
func (r *DatabaseRunner) executePostgres(ctx context.Context, req ExecutionRequest) (*ExecutionResult, error) {
	ctx, executionCancel := context.WithTimeout(ctx, 2*time.Minute)
	defer executionCancel()
	endpoint, err := url.Parse(r.cfg.PostgresURL)
	if err != nil || endpoint.Host == "" || (endpoint.Scheme != "postgres" && endpoint.Scheme != "postgresql") {
		return nil, fmt.Errorf("dedicated SQL sandbox URL is not configured")
	}
	if strings.TrimSpace(req.Query) == "" || len(req.Query) > maxSandboxSourceBytes {
		return nil, fmt.Errorf("SQL query must contain 1–32768 bytes")
	}
	if len(req.TestCases) > maxBatchTests {
		return nil, fmt.Errorf("SQL execution supports at most 50 tests")
	}
	token := make([]byte, 24)
	if _, err := rand.Read(token); err != nil {
		return nil, err
	}
	suffix := hex.EncodeToString(token[:8])
	role, schema := "sql_learner_"+suffix, "sql_fixture_"+suffix
	password := hex.EncodeToString(token[8:])
	admin, err := sql.Open("postgres", endpoint.String())
	if err != nil {
		return nil, err
	}
	defer admin.Close()
	admin.SetMaxOpenConns(1)
	setupCtx, setupCancel := context.WithTimeout(ctx, 15*time.Second)
	defer setupCancel()
	conn, err := admin.Conn(setupCtx)
	if err != nil {
		return nil, fmt.Errorf("SQL sandbox unavailable: %w", err)
	}
	defer conn.Close()
	if _, err := conn.ExecContext(setupCtx, "CREATE ROLE "+pq.QuoteIdentifier(role)+" LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 1 VALID UNTIL "+pq.QuoteLiteral(time.Now().Add(5*time.Minute).UTC().Format(time.RFC3339))+" PASSWORD "+pq.QuoteLiteral(password)); err != nil {
		return nil, fmt.Errorf("SQL sandbox could not create learner role: %w", err)
	}
	defer func() {
		cleanup, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		// A cancelled setup connection may be unusable; cleanup uses a new one.
		db, openErr := sql.Open("postgres", endpoint.String())
		if openErr != nil {
			return
		}
		defer db.Close()
		_, _ = db.ExecContext(cleanup, "DROP SCHEMA IF EXISTS "+pq.QuoteIdentifier(schema)+" CASCADE")
		_, _ = db.ExecContext(cleanup, "DROP ROLE IF EXISTS "+pq.QuoteIdentifier(role))
	}()
	learnerURL := *endpoint
	learnerURL.User = url.UserPassword(role, password)
	parameters := learnerURL.Query()
	parameters.Del("options")
	learnerURL.RawQuery = parameters.Encode()
	learner, err := sql.Open("postgres", learnerURL.String())
	if err != nil {
		return nil, err
	}
	defer learner.Close()
	learner.SetMaxOpenConns(1)
	tests := req.TestCases
	if len(tests) == 0 {
		tests = []TestCase{{ID: 0, Weight: 1}}
	}
	result := &ExecutionResult{Status: "ACCEPTED", MaxScore: 100, TotalTests: len(req.TestCases)}
	totalWeight, passedWeight := 0, 0
	for _, tc := range tests {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		fixtureCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
		err := func() error {
			tx, err := conn.BeginTx(fixtureCtx, nil)
			if err != nil {
				return err
			}
			defer tx.Rollback()
			_, err = tx.ExecContext(fixtureCtx, "DROP SCHEMA IF EXISTS "+pq.QuoteIdentifier(schema)+" CASCADE; CREATE SCHEMA "+pq.QuoteIdentifier(schema)+"; SET LOCAL search_path TO "+pq.QuoteIdentifier(schema))
			if err != nil {
				return err
			}
			// PostgreSQL parses the complete trusted fixture script, including quoted
			// semicolons and dollar-quoted functions; do not split it on semicolons.
			for _, script := range []string{req.SchemaSQL, req.SeedSQL, tc.Input} {
				if len(script) > 128*1024 {
					return fmt.Errorf("SQL fixture exceeds 128 KiB")
				}
				if strings.TrimSpace(script) != "" {
					if _, err := tx.ExecContext(fixtureCtx, script); err != nil {
						return err
					}
				}
			}
			if _, err := tx.ExecContext(fixtureCtx, "GRANT USAGE ON SCHEMA "+pq.QuoteIdentifier(schema)+" TO "+pq.QuoteIdentifier(role)+"; GRANT SELECT ON ALL TABLES IN SCHEMA "+pq.QuoteIdentifier(schema)+" TO "+pq.QuoteIdentifier(role)); err != nil {
				return err
			}
			return tx.Commit()
		}()
		cancel()
		if err != nil {
			return nil, fmt.Errorf("instructor SQL fixture could not be initialized: %w", err)
		}
		ms := configInt(req.RuntimeConfig, "time_limit_ms", 2000)
		if tc.TimeLimitMs > 0 {
			ms = tc.TimeLimitMs
		}
		if ms <= 0 || ms > 10000 {
			ms = 10000
		}
		queryCtx, queryCancel := context.WithTimeout(ctx, time.Duration(ms)*time.Millisecond)
		start := time.Now()
		actual, queryErr := func() (string, error) {
			tx, err := learner.BeginTx(queryCtx, &sql.TxOptions{ReadOnly: true})
			if err != nil {
				return "", err
			}
			defer tx.Rollback()
			if _, err := tx.ExecContext(queryCtx, "SET LOCAL search_path TO "+pq.QuoteIdentifier(schema)+"; SET LOCAL statement_timeout = "+fmt.Sprint(ms)); err != nil {
				return "", err
			}
			return queryPostgresCSV(queryCtx, tx, req.Query)
		}()
		status := "PASSED"
		if queryErr != nil {
			status = sqlErrorStatus(queryCtx, queryErr)
			actual = queryErr.Error()
		} else if len(req.TestCases) > 0 {
			ordered, _ := req.RuntimeConfig["order_sensitive"].(bool)
			if !compareSQLRows(actual, tc.Expected, ordered) {
				status = "WRONG_ANSWER"
			}
		}
		queryCancel()
		tr := TestResult{TestCaseID: tc.ID, Status: status, ActualOutput: actual, RuntimeMs: int(time.Since(start).Milliseconds())}
		result.RuntimeMs += tr.RuntimeMs
		result.TestResults = append(result.TestResults, tr)
		if status != "PASSED" && result.Status == "ACCEPTED" {
			result.Status = status
		}
		weight := tc.Weight
		if weight <= 0 {
			weight = 1
		}
		totalWeight += weight
		if status == "PASSED" {
			result.PassedTests++
			passedWeight += weight
		}
	}
	result.Score = 100 * float64(passedWeight) / float64(totalWeight)
	return result, nil
}

// Recover roles/fixtures left behind by a crashed API. Expiry exceeds the whole
// execution deadline, so this cannot delete an active submission's fixture.
func (r *DatabaseRunner) RunCleanup(ctx context.Context) {
	if r.cfg.PostgresURL == "" {
		return
	}
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()
	for {
		sweep, cancel := context.WithTimeout(ctx, 15*time.Second)
		db, err := sql.Open("postgres", r.cfg.PostgresURL)
		if err == nil {
			rows, err := db.QueryContext(sweep, "SELECT rolname FROM pg_roles WHERE rolname LIKE 'sql_learner_%' AND rolvaliduntil < now()")
			var roles []string
			if err == nil {
				for rows.Next() {
					var role string
					if rows.Scan(&role) == nil && strings.HasPrefix(role, "sql_learner_") {
						suffix := strings.TrimPrefix(role, "sql_learner_")
						if raw, err := hex.DecodeString(suffix); err == nil && len(raw) == 8 {
							roles = append(roles, role)
						}
					}
				}
				rows.Close()
				for _, role := range roles {
					schema := "sql_fixture_" + strings.TrimPrefix(role, "sql_learner_")
					_, _ = db.ExecContext(sweep, "DROP SCHEMA IF EXISTS "+pq.QuoteIdentifier(schema)+" CASCADE")
					_, _ = db.ExecContext(sweep, "DROP ROLE IF EXISTS "+pq.QuoteIdentifier(role))
				}
			}
			db.Close()
		}
		cancel()
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
