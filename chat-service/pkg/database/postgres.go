package database

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"chat-service/internal/config"
	"chat-service/pkg/logger"

	_ "github.com/jackc/pgx/v5/stdlib" // pgx stdlib driver
)

// NewPostgresDB opens a *sql.DB backed by pgx and configures the connection pool.
// Neon-safe tuning:
//   - prefer_simple_protocol=true   -> avoids prepared-statement conflicts through PgBouncer
//   - statement_cache_mode=describe -> safe for pooled connections
//   - connect_timeout=15            -> handle Neon cold-start (~2-3s)
//   - keepalives + tcp_keepalives   -> detect stale connections quickly
func NewPostgresDB(cfg config.DatabaseConfig) (*sql.DB, error) {
	// Build DSN with Neon-safe parameters
	dsn := fmt.Sprintf(
		"host=%s port=%s user=%s password=%s dbname=%s sslmode=%s"+
			" prefer_simple_protocol=true"+
			" statement_cache_mode=describe"+
			" connect_timeout=15"+
			" keepalives=1"+
			" keepalives_idle=30"+
			" keepalives_interval=10"+
			" keepalives_count=5"+
			" pool_max_conns=%d",
		cfg.Host, cfg.Port, cfg.User, cfg.Password, cfg.Name, cfg.SSLMode,
		cfg.MaxOpenConns,
	)

	logger.Infof("DB: connecting to %s@%s/%s (ssl=%s, pool=%d)",
		cfg.User, cfg.Host, cfg.Name, cfg.SSLMode, cfg.MaxOpenConns)

	db, err := sql.Open("pgx", dsn)
	if err != nil {
		return nil, fmt.Errorf("database: open: %w", err)
	}

	// Go-level pool limits (separate from pgx pool_max_conns)
	db.SetMaxOpenConns(cfg.MaxOpenConns)
	db.SetMaxIdleConns(cfg.MaxIdleConns)
	db.SetConnMaxLifetime(cfg.ConnMaxLifetime)
	db.SetConnMaxIdleTime(cfg.ConnMaxIdleTime)

	logger.Infof("DB: pool config - maxOpen=%d maxIdle=%d lifetime=%s idleTime=%s",
		cfg.MaxOpenConns, cfg.MaxIdleConns, cfg.ConnMaxLifetime, cfg.ConnMaxIdleTime)

	// Verify connectivity - allow up to 15s for Neon cold-start
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	start := time.Now()
	if err := db.PingContext(ctx); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("database: ping failed (Neon cold-start?): %w", err)
	}

	logger.Infof("DB: connected in %dms", time.Since(start).Milliseconds())
	return db, nil
}

// RunMigrations applies all .sql files from the migrations directory.
// Uses a simple schema_version table for idempotency.
func RunMigrations(db *sql.DB, migrationsDir string) error {
	// Ensure version table exists
	_, err := db.Exec(`
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version     VARCHAR(255) PRIMARY KEY,
			applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
		)`)
	if err != nil {
		return fmt.Errorf("migrations: create table: %w", err)
	}

	// Read and apply migrations in order
	entries, err := readMigrationFiles(migrationsDir)
	if err != nil {
		return err
	}

	for _, entry := range entries {
		var applied bool
		err := db.QueryRow(
			"SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version = $1)",
			entry.Version,
		).Scan(&applied)
		if err != nil {
			return fmt.Errorf("migrations: check version %s: %w", entry.Version, err)
		}
		if applied {
			continue
		}

		logger.Infof("Applying migration: %s", entry.Version)
		if _, err := db.Exec(entry.SQL); err != nil {
			return fmt.Errorf("migrations: apply %s: %w", entry.Version, err)
		}

		if _, err := db.Exec(
			"INSERT INTO schema_migrations (version) VALUES ($1)", entry.Version,
		); err != nil {
			return fmt.Errorf("migrations: record version %s: %w", entry.Version, err)
		}
	}

	return nil
}
