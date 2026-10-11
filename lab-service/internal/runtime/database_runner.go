package runtime

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"

	"lab-service/internal/config"

	// Import database drivers to register them
	"github.com/lib/pq"
)

type DatabaseRunner struct {
	slots chan struct{}
	cfg   config.DatabaseLabConfig
}

func NewDatabaseRunner(cfg config.DatabaseLabConfig) *DatabaseRunner {
	return &DatabaseRunner{cfg: cfg, slots: make(chan struct{}, 8)}
}

func (r *DatabaseRunner) Type() RuntimeType {
	return RuntimeDatabase
}

func (r *DatabaseRunner) Validate(values map[string]interface{}) error {
	engine, _ := values["db_type"].(string)
	if engine != "" && strings.ToUpper(engine) != "POSTGRESQL" {
		return fmt.Errorf("secure SQL practice currently supports PostgreSQL")
	}
	return nil
}

func (r *DatabaseRunner) Execute(ctx context.Context, req ExecutionRequest) (*ExecutionResult, error) {
	release, err := acquireExecutionSlot(ctx, r.slots)
	if err != nil {
		return nil, err
	}
	defer release()
	if err := r.Validate(req.RuntimeConfig); err != nil {
		return nil, err
	}
	return r.executePostgres(ctx, req)
}

// Inspect column metadata with LIMIT 0, then serialize bounded rows on the
// database side. Large generated values never travel into the API's row buffer.
func queryPostgresCSV(ctx context.Context, tx *sql.Tx, query string) (string, error) {
	query = strings.TrimRight(query, "; \t\r\n")
	relation := "(\n" + query + "\n) AS bdc_query"
	metadata, err := tx.QueryContext(ctx, "SELECT * FROM "+relation+" LIMIT 0")
	if err != nil {
		return "", err
	}
	columns, err := metadata.Columns()
	metadata.Close()
	if err != nil {
		return "", err
	}
	rows, err := tx.QueryContext(ctx, "SELECT CASE WHEN octet_length(row_to_json(bdc_query)::text) <= 65536 THEN row_to_json(bdc_query)::text ELSE NULL END FROM "+relation+" LIMIT 1001")
	if err != nil {
		return "", err
	}
	defer rows.Close()
	var buf bytes.Buffer
	writer := csv.NewWriter(&buf)
	if err := writer.Write(columns); err != nil {
		return "", err
	}
	count := 0
	for rows.Next() {
		count++
		if count > 1000 {
			return "", fmt.Errorf("SQL result exceeds 1000 rows")
		}
		var encoded sql.NullString
		if err := rows.Scan(&encoded); err != nil {
			return "", err
		}
		if !encoded.Valid {
			return "", fmt.Errorf("SQL row exceeds 64 KiB")
		}
		decoder := json.NewDecoder(strings.NewReader(encoded.String))
		if _, err := decoder.Token(); err != nil {
			return "", err
		}
		var record []string
		for decoder.More() {
			if _, err := decoder.Token(); err != nil {
				return "", err
			}
			var value json.RawMessage
			if err := decoder.Decode(&value); err != nil {
				return "", err
			}
			cell := string(value)
			if cell == "null" {
				cell = "NULL"
			} else if len(value) > 0 && value[0] == '"' {
				if err := json.Unmarshal(value, &cell); err != nil {
					return "", err
				}
			}
			record = append(record, cell)
		}
		if len(record) != len(columns) {
			return "", fmt.Errorf("SQL row metadata mismatch")
		}
		if err := writer.Write(record); err != nil {
			return "", err
		}
		writer.Flush()
		if err := writer.Error(); err != nil {
			return "", err
		}
		if buf.Len() > 64*1024 {
			return "", fmt.Errorf("SQL result exceeds 64 KiB")
		}
	}
	if err := rows.Err(); err != nil {
		return "", err
	}
	writer.Flush()
	return buf.String(), writer.Error()
}

func CompareSQLOutput(actual, expected string) bool { return compareSQLRows(actual, expected, true) }

func compareSQLRows(actual, expected string, ordered bool) bool {
	parse := func(value string) ([]string, error) {
		reader := csv.NewReader(strings.NewReader(strings.TrimRight(value, "\r\n")))
		reader.FieldsPerRecord = -1
		rows, err := reader.ReadAll()
		if err != nil {
			return nil, err
		}
		keys := make([]string, len(rows))
		for i, row := range rows {
			var buf bytes.Buffer
			writer := csv.NewWriter(&buf)
			_ = writer.Write(row)
			writer.Flush()
			keys[i] = buf.String()
		}
		if !ordered && len(keys) > 1 {
			sort.Strings(keys[1:])
		}
		return keys, nil
	}
	a, err := parse(actual)
	if err != nil {
		return false
	}
	e, err := parse(expected)
	if err != nil || len(a) != len(e) {
		return false
	}
	for i := range a {
		if a[i] != e[i] {
			return false
		}
	}
	return true
}

func sqlErrorStatus(ctx context.Context, err error) string {
	var pgErr *pq.Error
	if errors.As(err, &pgErr) && pgErr.Code == "57014" {
		return "TIME_LIMIT"
	}
	if errors.Is(ctx.Err(), context.DeadlineExceeded) || errors.Is(err, context.DeadlineExceeded) {
		return "TIME_LIMIT"
	}
	return "RUNTIME_ERROR"
}
