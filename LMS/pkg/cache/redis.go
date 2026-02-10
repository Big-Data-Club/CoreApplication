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

func KeyEnrollment(enrollmentID int64) string {
	return fmt.Sprintf("%s%d", PrefixEnrollment, enrollmentID)
}

func KeyStudentEnrollments(studentID int64) string {
	return fmt.Sprintf("%sstudent:%d", PrefixEnrollment, studentID)
}

func KeyCourseEnrollments(courseID int64) string {
	return fmt.Sprintf("%scourse:%d", PrefixEnrollment, courseID)
}

func KeyStudentProgress(enrollmentID int64) string {
	return fmt.Sprintf("%senrollment:%d", PrefixProgress, enrollmentID)
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

// NewRedisClient creates a new Redis client with config and tests connection
func NewRedisClient(cfg config.RedisConfig) (*RedisCache, error) {  // Giữ tên NewRedisClient
    client := redis.NewClient(&redis.Options{
        Addr:     fmt.Sprintf("%s:%s", cfg.Host, cfg.Port),
        Password: cfg.Password,
        DB:       cfg.DB,
    })

    ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()

    if err := client.Ping(ctx).Err(); err != nil {
        return nil, fmt.Errorf("failed to connect to Redis: %w", err)
    }

    return &RedisCache{client: client}, nil
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