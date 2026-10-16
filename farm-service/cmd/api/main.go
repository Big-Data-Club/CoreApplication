package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"bdc/farm-service/internal/farm"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/segmentio/kafka-go"
)

func required(key string) string {
	value := os.Getenv(key)
	if value == "" {
		slog.Error("missing required configuration", "key", key)
		os.Exit(1)
	}
	return value
}
func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	secret := required("JWT_SECRET")
	eventSecret := required("FARM_EVENT_SECRET")
	if len(secret) < 32 || len(eventSecret) < 32 {
		slog.Error("JWT_SECRET and FARM_EVENT_SECRET must each be at least 32 bytes")
		os.Exit(1)
	}
	databaseURL := os.Getenv("FARM_DATABASE_URL")
	if databaseURL == "" {
		for _, key := range []string{"PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD"} {
			required(key)
		}
	}
	config, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		slog.Error("invalid farm database configuration")
		os.Exit(1)
	}
	config.ConnConfig.ConnectTimeout = 5 * time.Second
	config.MaxConns = 10
	config.MinConns = 1
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		slog.Error("database pool failed")
		os.Exit(1)
	}
	defer pool.Close()
	store := &farm.Store{Pool: pool, Secret: eventSecret}
	migrationCtx, cancelMigration := context.WithTimeout(ctx, 30*time.Second)
	err = store.Migrate(migrationCtx)
	cancelMigration()
	if err != nil {
		slog.Error("farm schema initialization failed", "error", err)
		os.Exit(1)
	}
	writer := &kafka.Writer{Addr: kafka.TCP(strings.Split(required("KAFKA_BROKERS"), ",")...), Topic: farm.Topic, Balancer: &kafka.Hash{}, RequiredAcks: kafka.RequireAll, WriteTimeout: 5 * time.Second, AllowAutoTopicCreation: false}
	defer writer.Close()
	workerDone := make(chan struct{})
	go func() {
		defer close(workerDone)
		ticker := time.NewTicker(time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				for i := 0; i < 20; i++ {
					publishCtx, cancel := context.WithTimeout(ctx, 6*time.Second)
					sent, err := store.Dispatch(publishCtx, func(c context.Context, user int64, payload []byte) error {
						return writer.WriteMessages(c, kafka.Message{Key: []byte(strconv.FormatInt(user, 10)), Value: payload})
					})
					cancel()
					if err != nil {
						slog.Error("reward publication deferred; retained in outbox", "error", err)
						break
					}
					if !sent {
						break
					}
				}
			}
		}
	}()
	port := os.Getenv("PORT")
	if port == "" {
		port = "8087"
	}
	server := &http.Server{Addr: ":" + port, Handler: farm.Handler(store, secret), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 12 * time.Second, WriteTimeout: 15 * time.Second, IdleTimeout: 60 * time.Second}
	go func() {
		<-ctx.Done()
		c, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = server.Shutdown(c)
	}()
	slog.Info("knowledge farm listening", "port", port)
	if err = server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		slog.Error("HTTP server stopped", "error", err)
		stop()
	}
	stop()
	<-workerDone
}
