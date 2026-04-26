// pkg/cache/redis.go
package cache

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
	"example/hello/internal/config"
)

// Cache key prefixes
const (
	PrefixCourse      = "course:"
	PrefixSection     = "section:"
	PrefixContent     = "content:"
	PrefixEnrollment  = "enrollment:"
	PrefixProgress    = "progress:"
	PrefixQuiz        = "quiz:"
	PrefixAssignment  = "assignment:"
	PrefixUser        = "user:"
	PrefixSession     = "session:"

	KeyCourseList     = "courses:list:published"
)

// Cache key generators
func KeyCourse(courseID int64) string {
	return fmt.Sprintf("%s%d", PrefixCourse, courseID)
}

func KeyCourseTeachers(courseID int64) string {
	return fmt.Sprintf("%s%d:teachers", PrefixCourse, courseID)
}

func KeyCourseStats(courseID int64) string {
	return fmt.Sprintf("%s%d:stats", PrefixCourse, courseID)
}

func KeyCourseAnnouncements(courseID int64) string {
	return fmt.Sprintf("%s%d:announcements", PrefixCourse, courseID)
}

// KeyCourseSections caches the list of sections (metadata only) for a course.
// Used by the lazy-loading pattern: clients fetch the section list cheaply and
// only request individual content lists when a section expands in the UI.
func KeyCourseSections(courseID int64) string {
	return fmt.Sprintf("%s%d:sections", PrefixCourse, courseID)
}

func KeySection(sectionID int64) string {
	return fmt.Sprintf("%s%d", PrefixSection, sectionID)
}

// KeySectionContents caches the list of content items inside a section. The
// per-section grain keeps invalidation cheap when an instructor edits a single
// section without touching the rest of the course.
func KeySectionContents(sectionID int64) string {
	return fmt.Sprintf("%s%d:contents", PrefixSection, sectionID)
}

func KeyContent(contentID int64) string {
	return fmt.Sprintf("%s%d", PrefixContent, contentID)
}

func KeyEnrollment(enrollmentID int64) string {
	return fmt.Sprintf("%s%d", PrefixEnrollment, enrollmentID)
}

func KeyStudentEnrollments(studentID int64) string {
	return fmt.Sprintf("%sstudent:%d", PrefixEnrollment, studentID)
}

func KeyCourseEnrollments(courseID int64) string {
	return fmt.Sprintf("%scourse:%d", PrefixEnrollment, courseID)
}

// KeyStudentCourseEnrollment is the membership lookup hit on virtually every
// authenticated request that touches a course (VerifyAccess, ListSections,
// content visibility checks). Caching it removes a heavy hot-path query.
func KeyStudentCourseEnrollment(studentID, courseID int64) string {
	return fmt.Sprintf("%sstudent:%d:course:%d", PrefixEnrollment, studentID, courseID)
}

func KeyStudentProgress(enrollmentID int64) string {
	return fmt.Sprintf("%senrollment:%d", PrefixProgress, enrollmentID)
}

// KeyCourseProgress caches a student's aggregate progress for a course.
func KeyCourseProgress(courseID, studentID int64) string {
	return fmt.Sprintf("%scourse:%d:student:%d", PrefixProgress, courseID, studentID)
}

func KeyQuiz(quizID int64) string {
	return fmt.Sprintf("%s%d", PrefixQuiz, quizID)
}

func KeyQuizAttempt(attemptID int64) string {
	return fmt.Sprintf("%sattempt:%d", PrefixQuiz, attemptID)
}

func KeyStudentQuizAttempts(quizID, studentID int64) string {
	return fmt.Sprintf("%s%d:student:%d:attempts", PrefixQuiz, quizID, studentID)
}

func KeyAssignment(assignmentID int64) string {
	return fmt.Sprintf("%s%d", PrefixAssignment, assignmentID)
}

func KeyStudentSubmission(assignmentID, studentID int64) string {
	return fmt.Sprintf("%s%d:student:%d:submission", PrefixAssignment, assignmentID, studentID)
}

func KeyUserRoles(userID int64) string {
	return fmt.Sprintf("%s%d:roles", PrefixUser, userID)
}

// RedisCache wraps redis client with helper methods
type RedisCache struct {
	client *redis.Client
}

// NewRedisClient creates a new Redis client with config and tests connection.
//
// The pool/timeout knobs are intentionally surfaced through config: under load,
// the LMS service issues many concurrent Redis ops per HTTP request (rate
// limit, cache lookup, optional invalidation). Without a pool large enough to
// match in-flight Goroutines we'd see PoolTimeout errors before the database
// is even involved.
func NewRedisClient(cfg config.RedisConfig) (*RedisCache, error) {
	opts := &redis.Options{
		Addr:         fmt.Sprintf("%s:%s", cfg.Host, cfg.Port),
		Password:     cfg.Password,
		DB:           cfg.DB,
		PoolSize:     cfg.PoolSize,
		MinIdleConns: cfg.MinIdleConns,
		DialTimeout:  cfg.DialTimeout,
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
		PoolTimeout:  cfg.PoolTimeout,
	}

	// Defensive defaults if the caller passed a zero-value RedisConfig (e.g.
	// from older tests). These mirror the production tuning from config.Load.
	if opts.PoolSize == 0 {
		opts.PoolSize = 50
	}
	if opts.DialTimeout == 0 {
		opts.DialTimeout = 3 * time.Second
	}
	if opts.ReadTimeout == 0 {
		opts.ReadTimeout = 500 * time.Millisecond
	}
	if opts.WriteTimeout == 0 {
		opts.WriteTimeout = 500 * time.Millisecond
	}
	if opts.PoolTimeout == 0 {
		opts.PoolTimeout = 1 * time.Second
	}

	client := redis.NewClient(opts)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("failed to connect to Redis: %w", err)
	}

	return &RedisCache{client: client}, nil
}

// PoolStats exposes the underlying pool counters so the operator can wire them
// into Prometheus / health endpoints without leaking the redis client type.
func (c *RedisCache) PoolStats() *redis.PoolStats {
	return c.client.PoolStats()
}

// Get retrieves value from cache
func (c *RedisCache) Get(ctx context.Context, key string) (string, error) {
	return c.client.Get(ctx, key).Result()
}

// Set stores value in cache with expiration
func (c *RedisCache) Set(ctx context.Context, key string, value interface{}, expiration time.Duration) error {
	return c.client.Set(ctx, key, value, expiration).Err()
}

// Delete removes key from cache
func (c *RedisCache) Delete(ctx context.Context, keys ...string) error {
	return c.client.Del(ctx, keys...).Err()
}

// DeletePattern deletes all keys matching pattern
func (c *RedisCache) DeletePattern(ctx context.Context, pattern string) error {
	iter := c.client.Scan(ctx, 0, pattern, 0).Iterator()
	var keys []string
	
	for iter.Next(ctx) {
		keys = append(keys, iter.Val())
	}
	
	if err := iter.Err(); err != nil {
		return err
	}
	
	if len(keys) > 0 {
		return c.client.Del(ctx, keys...).Err()
	}
	
	return nil
}

// Exists checks if key exists
func (c *RedisCache) Exists(ctx context.Context, key string) (bool, error) {
	result, err := c.client.Exists(ctx, key).Result()
	return result > 0, err
}

// Increment increments integer value
func (c *RedisCache) Increment(ctx context.Context, key string) (int64, error) {
	return c.client.Incr(ctx, key).Result()
}

// IncrementWithExpiry increments and sets expiry if key is new
func (c *RedisCache) IncrementWithExpiry(ctx context.Context, key string, expiration time.Duration) (int64, error) {
	val, err := c.client.Incr(ctx, key).Result()
	if err != nil {
		return 0, err
	}
	
	if val == 1 {
		c.client.Expire(ctx, key, expiration)
	}
	
	return val, nil
}

// SetNX sets value only if key doesn't exist (for locks)
func (c *RedisCache) SetNX(ctx context.Context, key string, value interface{}, expiration time.Duration) (bool, error) {
	return c.client.SetNX(ctx, key, value, expiration).Result()
}

// GetSet atomically sets new value and returns old value
func (c *RedisCache) GetSet(ctx context.Context, key string, value interface{}) (string, error) {
	return c.client.GetSet(ctx, key, value).Result()
}

// HSet sets hash field
func (c *RedisCache) HSet(ctx context.Context, key, field string, value interface{}) error {
	return c.client.HSet(ctx, key, field, value).Err()
}

// HGet gets hash field
func (c *RedisCache) HGet(ctx context.Context, key, field string) (string, error) {
	return c.client.HGet(ctx, key, field).Result()
}

// HGetAll gets all hash fields
func (c *RedisCache) HGetAll(ctx context.Context, key string) (map[string]string, error) {
	return c.client.HGetAll(ctx, key).Result()
}

// HDel deletes hash fields
func (c *RedisCache) HDel(ctx context.Context, key string, fields ...string) error {
	return c.client.HDel(ctx, key, fields...).Err()
}

// ZAdd adds member to sorted set
func (c *RedisCache) ZAdd(ctx context.Context, key string, score float64, member interface{}) error {
	return c.client.ZAdd(ctx, key, redis.Z{Score: score, Member: member}).Err()
}

// ZRange gets sorted set members by rank
func (c *RedisCache) ZRange(ctx context.Context, key string, start, stop int64) ([]string, error) {
	return c.client.ZRange(ctx, key, start, stop).Result()
}

// ZRevRange gets sorted set members in reverse order
func (c *RedisCache) ZRevRange(ctx context.Context, key string, start, stop int64) ([]string, error) {
	return c.client.ZRevRange(ctx, key, start, stop).Result()
}

// Expire sets key expiration
func (c *RedisCache) Expire(ctx context.Context, key string, expiration time.Duration) error {
	return c.client.Expire(ctx, key, expiration).Err()
}

// TTL gets time to live
func (c *RedisCache) TTL(ctx context.Context, key string) (time.Duration, error) {
	return c.client.TTL(ctx, key).Result()
}

// Pipeline creates a pipeline for batch operations
func (c *RedisCache) Pipeline() redis.Pipeliner {
	return c.client.Pipeline()
}

// Close closes the redis connection
func (c *RedisCache) Close() error {
	return c.client.Close()
}

// HealthCheck checks if Redis is healthy
func (c *RedisCache) HealthCheck(ctx context.Context) error {
	return c.client.Ping(ctx).Err()
}

// MGet fetches multiple keys in one round-trip. Missing keys are returned as
// empty strings in the matching index, matching the upstream go-redis MGET
// semantics. Used for batch loaders (e.g. resolving N course IDs at once).
func (c *RedisCache) MGet(ctx context.Context, keys ...string) ([]string, error) {
	if len(keys) == 0 {
		return nil, nil
	}
	raw, err := c.client.MGet(ctx, keys...).Result()
	if err != nil {
		return nil, err
	}
	out := make([]string, len(raw))
	for i, v := range raw {
		if v == nil {
			continue
		}
		if s, ok := v.(string); ok {
			out[i] = s
		}
	}
	return out, nil
}