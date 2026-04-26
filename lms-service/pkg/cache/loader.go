// Package cache: loader.go
//
// This file builds a small "cache-aside with single-flight" helper on top of
// RedisCache. It targets the read-heavy CRUD endpoints in the LMS service
// where the same record (course, section, content, enrollment, …) is fetched
// hundreds of times per second.
//
// Why single-flight?
//
//   When a popular cache entry expires under load (the "thundering herd"
//   problem), every in-flight Goroutine simultaneously misses the cache and
//   races to reload the same row from Postgres. golang.org/x/sync/singleflight
//   collapses concurrent loads of the same key into a single DB round-trip;
//   the followers wait for the result and then proceed in lockstep.
//
// Why JSON encoding?
//
//   Most cached payloads are response DTOs that are already serialised as JSON
//   downstream. Storing the JSON form in Redis means the hot read path skips
//   re-encoding, and the same blob can be reused across handlers. JSON is also
//   debuggable from `redis-cli`.
//
// Negative caching is intentionally NOT done here. A "not found" should not
// be cached because in this domain rows are commonly created shortly after
// being looked up (e.g. enrollment immediately after course access check).
package cache

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/redis/go-redis/v9"
	"golang.org/x/sync/singleflight"
)

// ErrCacheMiss is returned by GetJSON when the key does not exist. Callers
// should treat it as a normal miss and fall back to the data source.
var ErrCacheMiss = errors.New("cache: miss")

// Loader wraps RedisCache with a singleflight group. One Loader per service
// instance is enough — singleflight keys are namespaced via the cache key.
type Loader struct {
	cache *RedisCache
	group singleflight.Group
}

// NewLoader builds a Loader bound to the given RedisCache. Pass the same
// RedisCache used by the rest of the service so cache keys collide correctly.
func NewLoader(c *RedisCache) *Loader {
	return &Loader{cache: c}
}

// Cache exposes the underlying RedisCache for callers that need raw ops
// (DELETE, pattern invalidation, increments, etc.).
func (l *Loader) Cache() *RedisCache {
	return l.cache
}

// GetJSON fetches a key and JSON-decodes it into out. Returns ErrCacheMiss if
// the key does not exist. Any other error (network, decode) is returned as-is
// so the caller can decide whether to fall back.
func GetJSON[T any](ctx context.Context, c *RedisCache, key string, out *T) error {
	raw, err := c.Get(ctx, key)
	if err != nil {
		if errors.Is(err, redis.Nil) {
			return ErrCacheMiss
		}
		return err
	}
	if raw == "" {
		return ErrCacheMiss
	}
	return json.Unmarshal([]byte(raw), out)
}

// SetJSON encodes value as JSON and stores it with the given TTL. A failure
// here is logged by the caller (cache writes are non-fatal) but propagated so
// tests can assert behaviour.
func SetJSON(ctx context.Context, c *RedisCache, key string, value any, ttl time.Duration) error {
	data, err := json.Marshal(value)
	if err != nil {
		return err
	}
	return c.Set(ctx, key, data, ttl)
}

// GetOrLoad implements cache-aside with single-flight protection.
//
//   1. Try the cache. On hit, decode and return.
//   2. On miss, exactly one Goroutine per (process, key) calls loader().
//      Concurrent callers wait for the same result.
//   3. Store the loader's result in the cache with TTL (best-effort) and
//      return it.
//
// `loader` is responsible for fetching from the source of truth (DB).
// If `loader` returns an error, neither the result nor a tombstone is cached.
func GetOrLoad[T any](
	ctx context.Context,
	l *Loader,
	key string,
	ttl time.Duration,
	loader func(ctx context.Context) (T, error),
) (T, error) {
	var zero T

	// Fast path: cache hit.
	var cached T
	if err := GetJSON(ctx, l.cache, key, &cached); err == nil {
		return cached, nil
	} else if !errors.Is(err, ErrCacheMiss) {
		// Decode or transport error — fall through to the loader rather than
		// poisoning the call site. Treat the cache as best-effort.
	}

	// Slow path: collapse concurrent misses into one DB round-trip.
	v, err, _ := l.group.Do(key, func() (any, error) {
		// Re-check cache inside the singleflight to avoid a redundant DB hit
		// when an earlier waiter already populated the entry.
		var doubleCheck T
		if err := GetJSON(ctx, l.cache, key, &doubleCheck); err == nil {
			return doubleCheck, nil
		}

		loaded, err := loader(ctx)
		if err != nil {
			return zero, err
		}

		// Best-effort write — cache failures should never break the request.
		_ = SetJSON(ctx, l.cache, key, loaded, ttl)
		return loaded, nil
	})

	if err != nil {
		return zero, err
	}
	// singleflight returns `any`; cast is safe because every branch above
	// produces a T (or an error).
	if typed, ok := v.(T); ok {
		return typed, nil
	}
	return zero, nil
}

// Invalidate is a thin convenience wrapper for the common write-path call
// pattern: after a mutating op succeeds, drop the related cache keys. Errors
// are intentionally swallowed — a stale entry will be evicted by TTL anyway,
// and we never want a Redis hiccup to fail an otherwise-successful write.
func Invalidate(ctx context.Context, c *RedisCache, keys ...string) {
	if len(keys) == 0 {
		return
	}
	_ = c.Delete(ctx, keys...)
}
