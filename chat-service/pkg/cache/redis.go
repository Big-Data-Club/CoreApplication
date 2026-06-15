package cache

import (
	"context"
	"fmt"
	"time"

	"chat-service/internal/config"
	"chat-service/pkg/logger"

	"github.com/redis/go-redis/v9"
)

// NewRedisClient creates a go-redis client tuned for high-throughput
// pub/sub and cache workloads. PoolSize should be at least
// (max expected pub/sub channels × 2) + HTTP handler pool.
func NewRedisClient(cfg config.RedisConfig) (*redis.Client, error) {
	addr := fmt.Sprintf("%s:%s", cfg.Host, cfg.Port)

	rdb := redis.NewClient(&redis.Options{
		Addr:         addr,
		Password:     cfg.Password,
		DB:           cfg.DB,
		PoolSize:     cfg.PoolSize,
		MinIdleConns: cfg.MinIdleConns,
		DialTimeout:  cfg.DialTimeout,
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
		PoolTimeout:  cfg.PoolTimeout,

		// Retry on network blips — important for Neon-hosted Redis
		MaxRetries:      3,
		MinRetryBackoff: 8 * time.Millisecond,
		MaxRetryBackoff: 512 * time.Millisecond,
	})

	logger.Infof("Redis: connecting to %s db=%d pool=%d minIdle=%d",
		addr, cfg.DB, cfg.PoolSize, cfg.MinIdleConns)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	start := time.Now()
	if _, err := rdb.Ping(ctx).Result(); err != nil {
		return nil, fmt.Errorf("redis: ping: %w", err)
	}

	logger.Infof("Redis: connected in %dms", time.Since(start).Milliseconds())
	return rdb, nil
}
