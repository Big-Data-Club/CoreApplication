package config

import (
	"fmt"
	"os"
	"strconv"
	"time"

	"github.com/joho/godotenv"
)

// Config holds all configuration for the application
type Config struct {
	App      AppConfig
	Database DatabaseConfig
	Redis    RedisConfig
	JWT      JWTConfig
	Storage  StorageConfig
	Server   ServerConfig
	Compiler CompilerConfig
}

// AppConfig holds application-specific configuration
type AppConfig struct {
	Name      string
	Env       string // development, staging, production
	Port      string
	LogLevel  string
}

// DatabaseConfig holds database connection configuration
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

// RedisConfig holds Redis configuration
type RedisConfig struct {
	Host         string
	Port         string
	Password     string
	DB           int
	PoolSize     int
	DialTimeout  time.Duration
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
}

// JWTConfig holds JWT configuration
type JWTConfig struct {
	Secret string
}

// StorageConfig holds storage configuration
type StorageConfig struct {
	Type           string // "local" or "minio"
	LocalBasePath  string
	MinIOEndpoint  string
	MinIOAccessKey string
	MinIOSecretKey string
	MinIOBucket    string
	MinIOUseSSL    bool
}

// ServerConfig holds server timeouts
type ServerConfig struct {
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
	IdleTimeout  time.Duration
}

// CompilerConfig holds LaTeX compiler settings
type CompilerConfig struct {
	WorkerCount int    // LATEX_WORKER_COUNT (default: 8)
	MaxTimeout  int    // LATEX_MAX_TIMEOUT seconds (default: 120)
	MaxMemoryMB int    // LATEX_MAX_MEMORY_MB (default: 512)
	TempDir     string // LATEX_TEMP_DIR (default: /tmp/latex-builds)
}

// Load loads configuration from environment variables
func Load() (*Config, error) {
	// Load .env file if exists (for development)
	_ = godotenv.Load()

	cfg := &Config{
		App: AppConfig{
			Name:     getEnv("APP_NAME", "LaTeX Service"),
			Env:      getEnv("APP_ENV", "development"),
			Port:     getEnv("LATEX_PORT", "8084"),
			LogLevel: getEnv("LOG_LEVEL", "INFO"),
		},

		Database: DatabaseConfig{
			Host:            getEnv("LATEX_DB_HOST", "localhost"),
			Port:            getEnv("LATEX_DB_PORT", "5437"),
			User:            getEnv("LATEX_DB_USER", "latexuser"),
			Password:        getEnv("LATEX_DB_PASSWORD", "latexpass"),
			Name:            getEnv("LATEX_DB_NAME", "latexdb"),
			SSLMode:         getEnv("LATEX_DB_SSLMODE", "disable"),
			MaxOpenConns:    getEnvAsInt("LATEX_DB_MAX_OPEN_CONNS", 25),
			MaxIdleConns:    getEnvAsInt("LATEX_DB_MAX_IDLE_CONNS", 25),
			ConnMaxLifetime: getEnvAsDuration("LATEX_DB_CONN_MAX_LIFETIME", 5*time.Minute),
			ConnMaxIdleTime: getEnvAsDuration("LATEX_DB_CONN_MAX_IDLE_TIME", 5*time.Minute),
		},

		Redis: RedisConfig{
			Host:         getEnv("REDIS_HOST", "localhost"),
			Port:         getEnv("REDIS_PORT", "6379"),
			Password:     getEnv("REDIS_PASSWORD", ""),
			DB:           getEnvAsInt("REDIS_DB", 4), // DB 4 assigned to LaTeX
			PoolSize:     getEnvAsInt("REDIS_POOL_SIZE", 50),
			DialTimeout:  getEnvAsDuration("REDIS_DIAL_TIMEOUT", 3*time.Second),
			ReadTimeout:  getEnvAsDuration("REDIS_READ_TIMEOUT", 500*time.Millisecond),
			WriteTimeout: getEnvAsDuration("REDIS_WRITE_TIMEOUT", 500*time.Millisecond),
		},

		JWT: JWTConfig{
			Secret: getEnv("JWT_SECRET", "very_secret_key_change_me_please"),
		},

		Storage: StorageConfig{
			Type:           getEnv("STORAGE_TYPE", "minio"),
			LocalBasePath:  getEnv("STORAGE_LOCAL_PATH", "./uploads"),
			MinIOEndpoint:  getEnv("MINIO_ENDPOINT", "localhost:9000"),
			MinIOAccessKey: getEnv("MINIO_ACCESS_KEY", "minioadmin"),
			MinIOSecretKey: getEnv("MINIO_SECRET_KEY", "minioadmin123"),
			MinIOBucket:    getEnv("LATEX_MINIO_BUCKET", "latex-files"),
			MinIOUseSSL:    getEnv("MINIO_USE_SSL", "false") == "true",
		},

		Server: ServerConfig{
			ReadTimeout:  getEnvAsDuration("SERVER_READ_TIMEOUT", 5*time.Minute),
			WriteTimeout: getEnvAsDuration("SERVER_WRITE_TIMEOUT", 5*time.Minute),
			IdleTimeout:  getEnvAsDuration("SERVER_IDLE_TIMEOUT", 600*time.Second),
		},

		Compiler: CompilerConfig{
			WorkerCount: getEnvAsInt("LATEX_WORKER_COUNT", 8),
			MaxTimeout:  getEnvAsInt("LATEX_MAX_TIMEOUT", 120),
			MaxMemoryMB: getEnvAsInt("LATEX_MAX_MEMORY_MB", 512),
			TempDir:     getEnv("LATEX_TEMP_DIR", "/tmp/latex-builds"),
		},
	}

	// Validate required fields
	if err := cfg.Validate(); err != nil {
		return nil, err
	}

	return cfg, nil
}

// Validate validates the configuration
func (c *Config) Validate() error {
	if c.Database.Host == "" {
		return fmt.Errorf("database host is required")
	}
	if c.Database.Name == "" {
		return fmt.Errorf("database name is required")
	}
	if c.Database.User == "" {
		return fmt.Errorf("database user is required")
	}
	if c.JWT.Secret == "" || c.JWT.Secret == "very_secret_key_change_me_please" {
		if c.App.Env == "production" {
			return fmt.Errorf("JWT secret must be set in production")
		}
	}
	if len(c.JWT.Secret) < 32 {
		return fmt.Errorf("JWT secret must be at least 32 characters")
	}
	return nil
}

// GetDSN returns the database connection string
func (c *Config) GetDSN() string {
	return fmt.Sprintf(
		"host=%s port=%s user=%s password=%s dbname=%s sslmode=%s",
		c.Database.Host,
		c.Database.Port,
		c.Database.User,
		c.Database.Password,
		c.Database.Name,
		c.Database.SSLMode,
	)
}

// GetRedisAddr returns the Redis address
func (c *Config) GetRedisAddr() string {
	return fmt.Sprintf("%s:%s", c.Redis.Host, c.Redis.Port)
}

// Helper functions

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvAsInt(key string, defaultValue int) int {
	valueStr := getEnv(key, "")
	if value, err := strconv.Atoi(valueStr); err == nil {
		return value
	}
	return defaultValue
}

func getEnvAsDuration(key string, defaultValue time.Duration) time.Duration {
	valueStr := getEnv(key, "")
	if value, err := time.ParseDuration(valueStr); err == nil {
		return value
	}
	return defaultValue
}
