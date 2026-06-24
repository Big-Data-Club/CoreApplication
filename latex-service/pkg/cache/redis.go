package cache

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
	"latex-service/internal/config"
)

// RedisCache wraps redis client with helper methods
type RedisCache struct {
	client *redis.Client
}

// NewRedisClient creates a new Redis client
func NewRedisClient(cfg config.RedisConfig) (*RedisCache, error) {
	opts := &redis.Options{
		Addr:         fmt.Sprintf("%s:%s", cfg.Host, cfg.Port),
		Password:     cfg.Password,
		DB:           cfg.DB,
		PoolSize:     cfg.PoolSize,
		DialTimeout:  cfg.DialTimeout,
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
	}

	client := redis.NewClient(opts)

	// Test connection
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("failed to ping redis: %w", err)
	}

	return &RedisCache{client: client}, nil
}

// GetClient returns the underlying redis client
func (r *RedisCache) GetClient() *redis.Client {
	return r.client
}

// Get gets a value from cache
func (r *RedisCache) Get(ctx context.Context, key string) (string, error) {
	return r.client.Get(ctx, key).Result()
}

// Set sets a value in cache with expiration
func (r *RedisCache) Set(ctx context.Context, key string, value interface{}, expiration time.Duration) error {
	return r.client.Set(ctx, key, value, expiration).Err()
}

// Delete deletes a key from cache
func (r *RedisCache) Delete(ctx context.Context, key string) error {
	return r.client.Del(ctx, key).Err()
}

// Exists checks if a key exists
func (r *RedisCache) Exists(ctx context.Context, key string) (bool, error) {
	count, err := r.client.Exists(ctx, key).Result()
	return count > 0, err
}

var incrWithExpiryScript = redis.NewScript(`
	local current = redis.call('INCR', KEYS[1])
	if current == 1 then
		redis.call('PEXPIRE', KEYS[1], ARGV[1])
	else
		local ttl = redis.call('TTL', KEYS[1])
		if ttl == -1 then
			redis.call('PEXPIRE', KEYS[1], ARGV[1])
		end
	end
	return current
`)

// IncrementWithExpiry increments and sets expiry if key is new
func (r *RedisCache) IncrementWithExpiry(ctx context.Context, key string, expiration time.Duration) (int64, error) {
	ms := expiration.Milliseconds()
	if ms <= 0 {
		ms = 1
	}

	res, err := incrWithExpiryScript.Run(ctx, r.client, []string{key}, ms).Result()
	if err != nil {
		return 0, err
	}

	switch v := res.(type) {
	case int:
		return int64(v), nil
	case int64:
		return v, nil
	default:
		return 0, fmt.Errorf("unexpected return type from redis script: %T", res)
	}
}

