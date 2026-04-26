// pkg/database/postgres.go
package database

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	_ "github.com/lib/pq"
	"example/hello/internal/config"
)

// NewPostgresDB creates a new PostgreSQL database connection
func NewPostgresDB(cfg config.DatabaseConfig) (*sql.DB, error) {
	// Build connection string
	dsn := fmt.Sprintf(
		"host=%s port=%s user=%s password=%s dbname=%s sslmode=%s",
		cfg.Host,
		cfg.Port,
		cfg.User,
		cfg.Password,
		cfg.Name,
		cfg.SSLMode,
	)

	// Open database connection
	db, err := sql.Open("postgres", dsn)
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