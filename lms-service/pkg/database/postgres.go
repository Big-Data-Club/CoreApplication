// pkg/database/postgres.go
package database

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"example/hello/internal/config"
	_ "github.com/jackc/pgx/v5/stdlib"
)

// NewPostgresDB creates a new PostgreSQL database connection
func NewPostgresDB(cfg config.DatabaseConfig) (*sql.DB, error) {
	// Build connection string.
	// We use pgx driver and set default_query_exec_mode=simple_protocol
	// to avoid "bind message supplies X parameters" and "unnamed prepared statement does not exist"
	// errors when running behind PgBouncer in transaction pooling mode.
	dsn := fmt.Sprintf(
		"host=%s port=%s user=%s password=%s dbname=%s sslmode=%s default_query_exec_mode=simple_protocol",
		cfg.Host,
		cfg.Port,
		cfg.User,
		cfg.Password,
		cfg.Name,
		cfg.SSLMode,
	)

	// Open database connection
	db, err := sql.Open("pgx", dsn)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	// Set connection pool settings.
	//
	// Sizing rationale for an HTTP service on top of pgx/lib-pq:
	//   - MaxOpenConns caps concurrent in-flight queries and protects Postgres
	//     from connection storms during traffic spikes.
	//   - MaxIdleConns is kept high enough to absorb bursty traffic without
	//     paying the TCP/TLS handshake on every request, but low enough to free
	//     server resources during idle periods.
	//   - ConnMaxLifetime forces periodic reconnects so PgBouncer/HAProxy can
	//     rebalance and prepared-statement plans don't grow unboundedly.
	//   - ConnMaxIdleTime trims the pool back to MaxIdleConns between bursts,
	//     which matters for multi-tenant deployments that share one Postgres.
	db.SetMaxOpenConns(cfg.MaxOpenConns)
	db.SetMaxIdleConns(cfg.MaxIdleConns)
	db.SetConnMaxLifetime(cfg.ConnMaxLifetime)
	if cfg.ConnMaxIdleTime > 0 {
		db.SetConnMaxIdleTime(cfg.ConnMaxIdleTime)
	}

	// Verify connection
	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	return db, nil
}

// EnsureTeacherDashboardIndexes applies the small, idempotent index set needed
// by the teacher dashboard. It runs asynchronously at service startup so a
// first-time index build never blocks readiness or a deployment rollout.
//
// The statements deliberately use IF NOT EXISTS; after the first successful
// run they are effectively no-ops. Errors are returned to the caller for
// logging but must not take the LMS offline.
func EnsureTeacherDashboardIndexes(ctx context.Context, db *sql.DB) error {
	statements := []string{
		`CREATE INDEX IF NOT EXISTS idx_courses_teacher_published ON courses(created_by, id) WHERE status = 'PUBLISHED'`,
		`CREATE INDEX IF NOT EXISTS idx_enrollments_accepted_timeline ON enrollments(course_id, enrolled_at DESC, student_id) WHERE status = 'ACCEPTED'`,
		`CREATE INDEX IF NOT EXISTS idx_quiz_attempts_dashboard_first ON quiz_attempts(quiz_id, student_id, attempt_number, id) INCLUDE (percentage) WHERE status IN ('SUBMITTED', 'GRADED')`,
	}
	for _, statement := range statements {
		if _, err := db.ExecContext(ctx, statement); err != nil {
			return err
		}
	}
	return nil
}

// HealthCheck checks if database is healthy
func HealthCheck(db *sql.DB) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	return db.PingContext(ctx)
}

// Close closes the database connection
func Close(db *sql.DB) error {
	return db.Close()
}
