package runtime

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/csv"
	"fmt"
	"strings"
	"time"

	"lab-service/internal/config"
	"lab-service/pkg/logger"

	// Import database drivers to register them
	_ "github.com/go-sql-driver/mysql"
	_ "github.com/lib/pq"
	_ "github.com/microsoft/go-mssqldb"
	_ "github.com/sijms/go-ora/v2"
)

type DatabaseRunner struct {
	cfg config.DatabaseLabConfig
}

func NewDatabaseRunner(cfg config.DatabaseLabConfig) *DatabaseRunner {
	return &DatabaseRunner{cfg: cfg}
}

func (r *DatabaseRunner) Type() RuntimeType {
	return RuntimeDatabase
}

func (r *DatabaseRunner) Validate(config map[string]interface{}) error {
	return nil
}

func (r *DatabaseRunner) Execute(ctx context.Context, req ExecutionRequest) (*ExecutionResult, error) {
	logger.Info(fmt.Sprintf("DatabaseRunner: executing SQL query for submission %d", req.SubmissionID))

	dbType := "POSTGRESQL"
	if t, ok := req.RuntimeConfig["db_type"]; ok {
		if s, ok := t.(string); ok {
			dbType = strings.ToUpper(s)
		}
	}

	var driverName, connectionURL string
	switch dbType {
	case "POSTGRESQL":
		driverName = "postgres"
		connectionURL = r.cfg.PostgresURL
	case "MYSQL":
		driverName = "mysql"
		connectionURL = r.cfg.MySQLURL
	case "SQLSERVER":
		driverName = "sqlserver"
		connectionURL = r.cfg.SQLServerURL
	case "ORACLE":
		driverName = "oracle"
		connectionURL = r.cfg.OracleURL
	default:
		return nil, fmt.Errorf("unsupported database type: %s", dbType)
	}

	if connectionURL == "" {
		return nil, fmt.Errorf("connection URL for %s database is not configured", dbType)
	}

	// Dial target database
	db, err := sql.Open(driverName, connectionURL)
	if err != nil {
		return nil, fmt.Errorf("failed to open database connection: %w", err)
	}
	defer db.Close()

	// Verify connection
	pingCtx, pingCancel := context.WithTimeout(ctx, 3*time.Second)
	defer pingCancel()
	if err := db.PingContext(pingCtx); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	// Setup unique isolation schema/database
	sessionID := fmt.Sprintf("temp_lab_%d_%d", req.SubmissionID, time.Now().UnixNano()%1000000)
	
	var schemaName string
	var cleanupQuery string
	var useQuery string

	switch dbType {
	case "POSTGRESQL":
		schemaName = sessionID
		useQuery = fmt.Sprintf("SET search_path TO %s;", schemaName)
		cleanupQuery = fmt.Sprintf("DROP SCHEMA %s CASCADE;", schemaName)

	case "MYSQL":
		schemaName = sessionID
		useQuery = fmt.Sprintf("USE %s;", schemaName)
		cleanupQuery = fmt.Sprintf("DROP DATABASE %s;", schemaName)

	case "SQLSERVER":
		schemaName = sessionID
		useQuery = fmt.Sprintf("USE %s;", schemaName)
		cleanupQuery = fmt.Sprintf("ALTER DATABASE %s SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE %s;", schemaName, schemaName)

	case "ORACLE":
		schemaName = strings.ToUpper(sessionID)
		useQuery = fmt.Sprintf("ALTER SESSION SET CURRENT_SCHEMA = %s;", schemaName)
		cleanupQuery = fmt.Sprintf("DROP USER %s CASCADE;", schemaName)
	}

	// Perform database setup
	if dbType == "SQLSERVER" {
		if _, err := db.ExecContext(ctx, fmt.Sprintf("CREATE DATABASE %s;", schemaName)); err != nil {
			return nil, fmt.Errorf("failed to create MSSQL temp database: %w", err)
		}
		if _, err := db.ExecContext(ctx, fmt.Sprintf("USE %s;", schemaName)); err != nil {
			db.ExecContext(context.Background(), fmt.Sprintf("DROP DATABASE %s;", schemaName))
			return nil, fmt.Errorf("failed to USE MSSQL temp database: %w", err)
		}
	} else if dbType == "ORACLE" {
		statements := []string{
			fmt.Sprintf("CREATE USER %s IDENTIFIED BY Password123", schemaName),
			fmt.Sprintf("GRANT CONNECT, RESOURCE, CREATE VIEW TO %s", schemaName),
			fmt.Sprintf("ALTER USER %s QUOTA UNLIMITED ON USERS", schemaName),
		}
		for _, stmt := range statements {
			if _, err := db.ExecContext(ctx, stmt); err != nil {
				db.ExecContext(context.Background(), fmt.Sprintf("DROP USER %s CASCADE", schemaName))
				return nil, fmt.Errorf("failed to setup Oracle temp user: %w", err)
			}
		}
		if _, err := db.ExecContext(ctx, useQuery); err != nil {
			db.ExecContext(context.Background(), fmt.Sprintf("DROP USER %s CASCADE", schemaName))
			return nil, fmt.Errorf("failed to switch to Oracle temp schema: %w", err)
		}
	} else {
		if dbType == "POSTGRESQL" {
			if _, err := db.ExecContext(ctx, fmt.Sprintf("CREATE SCHEMA %s;", schemaName)); err != nil {
				return nil, fmt.Errorf("failed to create Postgres temp schema: %w", err)
			}
		} else if dbType == "MYSQL" {
			if _, err := db.ExecContext(ctx, fmt.Sprintf("CREATE DATABASE %s;", schemaName)); err != nil {
				return nil, fmt.Errorf("failed to create MySQL temp database: %w", err)
			}
		}
		if _, err := db.ExecContext(ctx, useQuery); err != nil {
			return nil, fmt.Errorf("failed to target temp schema/database context: %w", err)
		}
	}

	// Defer cleanup to drop the schema/database
	defer func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cleanupCancel()
		if dbType == "SQLSERVER" {
			db.ExecContext(cleanupCtx, "USE master;")
		}
		_, err := db.ExecContext(cleanupCtx, cleanupQuery)
		if err != nil {
			logger.Error(fmt.Sprintf("DatabaseRunner: failed to clean up temp schema/database %s: %v", schemaName, err), err)
		}
	}()

	// Run Schema DDL SQL
	if req.SchemaSQL != "" {
		if err := executeSQLScript(ctx, db, req.SchemaSQL, dbType); err != nil {
			return &ExecutionResult{
				Status:         "RUNTIME_ERROR",
				CompilerOutput: fmt.Sprintf("Schema DDL execution failed: %v", err),
			}, nil
		}
	}

	// Run Seed Data SQL
	if req.SeedSQL != "" {
		if err := executeSQLScript(ctx, db, req.SeedSQL, dbType); err != nil {
			return &ExecutionResult{
				Status:         "RUNTIME_ERROR",
				CompilerOutput: fmt.Sprintf("Seed data insertion failed: %v", err),
			}, nil
		}
	}

	result := &ExecutionResult{
		TotalTests: len(req.TestCases),
		MaxScore:   100,
	}

	if len(req.TestCases) == 0 {
		startTime := time.Now()
		rows, err := db.QueryContext(ctx, req.Query)
		duration := int(time.Since(startTime).Milliseconds())
		if err != nil {
			result.Status = "RUNTIME_ERROR"
			result.Stderr = err.Error()
			return result, nil
		}
		rows.Close()
		result.Status = "ACCEPTED"
		result.Score = 100
		result.RuntimeMs = duration
		return result, nil
	}

	totalWeight := 0
	passedWeight := 0
	totalRuntime := 0

	for _, tc := range req.TestCases {
		totalWeight += tc.Weight

		startTime := time.Now()
		rows, qErr := db.QueryContext(ctx, req.Query)
		duration := int(time.Since(startTime).Milliseconds())
		totalRuntime += duration

		if qErr != nil {
			tr := TestResult{
				TestCaseID:   tc.ID,
				Status:       "RUNTIME_ERROR",
				ActualOutput: qErr.Error(),
				RuntimeMs:    duration,
			}
			result.TestResults = append(result.TestResults, tr)
			continue
		}

		actualCSV, formatErr := formatRowsToCSV(rows)
		rows.Close()

		if formatErr != nil {
			tr := TestResult{
				TestCaseID:   tc.ID,
				Status:       "RUNTIME_ERROR",
				ActualOutput: fmt.Sprintf("Failed to format database rows: %v", formatErr),
				RuntimeMs:    duration,
			}
			result.TestResults = append(result.TestResults, tr)
			continue
		}

		if CompareSQLOutput(actualCSV, tc.Expected) {
			tr := TestResult{
				TestCaseID:   tc.ID,
				Status:       "PASSED",
				ActualOutput: actualCSV,
				RuntimeMs:    duration,
			}
			result.TestResults = append(result.TestResults, tr)
			result.PassedTests++
			passedWeight += tc.Weight
		} else {
			tr := TestResult{
				TestCaseID:   tc.ID,
				Status:       "WRONG_ANSWER",
				ActualOutput: actualCSV,
				RuntimeMs:    duration,
			}
			result.TestResults = append(result.TestResults, tr)
		}
	}

	result.RuntimeMs = totalRuntime
	if result.PassedTests == result.TotalTests {
		result.Status = "ACCEPTED"
	} else {
		result.Status = "WRONG_ANSWER"
	}

	if totalWeight > 0 {
		result.Score = float64(passedWeight) / float64(totalWeight) * result.MaxScore
	}

	return result, nil
}

func executeSQLScript(ctx context.Context, db *sql.DB, script string, dbType string) error {
	statements := strings.Split(script, ";")
	for _, stmt := range statements {
		trimmed := strings.TrimSpace(stmt)
		if trimmed == "" {
			continue
		}
		if dbType == "SQLSERVER" && strings.ToUpper(trimmed) == "GO" {
			continue
		}
		if _, err := db.ExecContext(ctx, trimmed); err != nil {
			return fmt.Errorf("SQL error executing stmt %q: %w", trimmed, err)
		}
	}
	return nil
}

func formatRowsToCSV(rows *sql.Rows) (string, error) {
	columns, err := rows.Columns()
	if err != nil {
		return "", err
	}

	var buf bytes.Buffer
	writer := csv.NewWriter(&buf)

	if err := writer.Write(columns); err != nil {
		return "", err
	}

	values := make([]interface{}, len(columns))
	valuePtrs := make([]interface{}, len(columns))
	for i := range columns {
		valuePtrs[i] = &values[i]
	}

	for rows.Next() {
		if err := rows.Scan(valuePtrs...); err != nil {
			return "", err
		}

		record := make([]string, len(columns))
		for i, val := range values {
			if val == nil {
				record[i] = "NULL"
			} else {
				switch v := val.(type) {
				case []byte:
					record[i] = string(v)
				default:
					record[i] = fmt.Sprintf("%v", v)
				}
			}
		}

		if err := writer.Write(record); err != nil {
			return "", err
		}
	}
	writer.Flush()
	return buf.String(), nil
}

func CompareSQLOutput(actual, expected string) bool {
	a := normalizeLines(actual)
	e := normalizeLines(expected)
	return a == e
}

func normalizeLines(s string) string {
	lines := strings.Split(s, "\n")
	var result []string
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed != "" {
			trimmed = strings.ReplaceAll(trimmed, ";", ",")
			result = append(result, trimmed)
		}
	}
	return strings.Join(result, "\n")
}
