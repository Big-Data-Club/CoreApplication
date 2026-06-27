package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/joho/godotenv"
)

// Config holds all application configuration loaded from environment variables.
type Config struct {
	App      AppConfig
	Database DatabaseConfig
	Redis    RedisConfig
	JWT      JWTConfig
	CORS     CORSConfig
	Server   ServerConfig
	Sync     SyncConfig
}

type AppConfig struct {
	Name     string
	Env      string
	Port     string
	LogLevel string
}

type DatabaseConfig struct {
	Host            string
	Port            string
	User            string
	Password        string
	Name            string
	SSLMode         string
	MaxOpenConns    int
	MaxIdleConns    int
	ConnMaxLifetime time.Duration
	ConnMaxIdleTime time.Duration
}

// RedisConfig is tuned for high-throughput pub/sub + cache.
// PoolSize should cover (WS connections × channels per conn × publish rate).
type RedisConfig struct {
	Host         string
	Port         string
	Password     string
	DB           int
	PoolSize     int
	MinIdleConns int
	DialTimeout  time.Duration
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
	PoolTimeout  time.Duration
}

type JWTConfig struct {
	Secret string
}

type CORSConfig struct {
	AllowedOrigins []string
}

type ServerConfig struct {
	ReadTimeout       time.Duration
	WriteTimeout      time.Duration
	IdleTimeout       time.Duration
	ShutdownTimeout   time.Duration
	// MaxConnectionsPerIP limits WS upgrade attempts (brute-force mitigation)
	MaxConnectionsPerIP int
}

// SyncConfig holds the shared secret used by auth-service to push user data.
type SyncConfig struct {
	Secret string
}

// Load reads configuration from environment (with .env fallback in dev).
func Load() (*Config, error) {
	// Best-effort .env load - no error in production where vars come from Docker/k8s
	_ = godotenv.Load("../../.env")
	_ = godotenv.Load(".env")

	cfg := &Config{
		App: AppConfig{
			Name:     getEnv("APP_NAME", "Chat Service"),
			Env:      getEnv("APP_ENV", "development"),
			Port:     getEnv("APP_PORT", "8083"),
			LogLevel: getEnv("LOG_LEVEL", "INFO"),
		},
		Database: DatabaseConfig{
			Host:            requireEnv("DB_HOST"),
			Port:            getEnv("DB_PORT", "5432"),
			User:            requireEnv("DB_USER"),
			Password:        requireEnv("DB_PASSWORD"),
			Name:            requireEnv("DB_NAME"),
			SSLMode:         getEnv("DB_SSL_MODE", "require"),
			MaxOpenConns:    getEnvInt("DB_MAX_OPEN_CONNS", 30),
			MaxIdleConns:    getEnvInt("DB_MAX_IDLE_CONNS", 5),
			ConnMaxLifetime: getEnvDuration("DB_CONN_MAX_LIFETIME", 30*time.Minute),
			ConnMaxIdleTime: getEnvDuration("DB_CONN_MAX_IDLE_TIME", 5*time.Minute),
		},
		Redis: RedisConfig{
			Host:         getEnv("REDIS_HOST", "localhost"),
			Port:         getEnv("REDIS_PORT", "6379"),
			Password:     getEnv("REDIS_PASSWORD", ""),
			DB:           getEnvInt("REDIS_DB", 3),
			PoolSize:     getEnvInt("REDIS_POOL_SIZE", 100),
			MinIdleConns: getEnvInt("REDIS_MIN_IDLE_CONNS", 10),
			DialTimeout:  getEnvDuration("REDIS_DIAL_TIMEOUT", 3*time.Second),
			ReadTimeout:  getEnvDuration("REDIS_READ_TIMEOUT", 500*time.Millisecond),
			WriteTimeout: getEnvDuration("REDIS_WRITE_TIMEOUT", 500*time.Millisecond),
			PoolTimeout:  getEnvDuration("REDIS_POOL_TIMEOUT", 1*time.Second),
		},
		JWT: JWTConfig{
			Secret: requireEnv("JWT_SECRET"),
		},
		CORS: CORSConfig{
			AllowedOrigins: strings.Split(getEnv("CORS_ALLOWED_ORIGINS", "http://localhost:3000"), ","),
		},
		Server: ServerConfig{
			ReadTimeout:         getEnvDuration("SERVER_READ_TIMEOUT", 10*time.Second),
			WriteTimeout:        getEnvDuration("SERVER_WRITE_TIMEOUT", 0), // 0 = no timeout (WS needs this)
			IdleTimeout:         getEnvDuration("SERVER_IDLE_TIMEOUT", 60*time.Second),
			ShutdownTimeout:     getEnvDuration("SERVER_SHUTDOWN_TIMEOUT", 15*time.Second),
			MaxConnectionsPerIP: getEnvInt("MAX_CONNECTIONS_PER_IP", 20),
		},
		Sync: SyncConfig{
			Secret: requireEnv("CHAT_SYNC_SECRET"),
		},
	}

	return cfg, nil
}

func (d *DatabaseConfig) DSN() string {
	return fmt.Sprintf(
		"host=%s port=%s user=%s password=%s dbname=%s sslmode=%s "+
			"pool_max_conns=%d pool_min_conns=%d "+
			"pool_max_conn_lifetime=%s pool_max_conn_idle_time=%s",
		d.Host, d.Port, d.User, d.Password, d.Name, d.SSLMode,
		d.MaxOpenConns, d.MaxIdleConns,
		d.ConnMaxLifetime, d.ConnMaxIdleTime,
	)
}

// ── helpers ──────────────────────────────────────────────────────────────────

func getEnv(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}

func requireEnv(key string) string {
	v := os.Getenv(key)
	if v == "" {
		panic(fmt.Sprintf("required environment variable %q is not set", key))
	}
	return v
}

func getEnvInt(key string, defaultVal int) int {
	v := os.Getenv(key)
	if v == "" {
		return defaultVal
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return defaultVal
	}
	return n
}

func getEnvDuration(key string, defaultVal time.Duration) time.Duration {
	v := os.Getenv(key)
	if v == "" {
		return defaultVal
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return defaultVal
	}
	return d
}
