package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/joho/godotenv"
)

// Config holds all configuration for the application
type Config struct {
	App      AppConfig
	Database DatabaseConfig
	Redis    RedisConfig
	JWT      JWTConfig
	Upload   UploadConfig
	Storage  StorageConfig
	CORS     CORSConfig
	Server   ServerConfig
	Email    EmailConfig
}

// AppConfig holds application-specific configuration
type AppConfig struct {
	Name        string
	Env         string // development, staging, production
	Port        string
	Version     string
	BuildDate   string
	LogLevel    string
	LogFormat   string // json, text
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
}

// RedisConfig holds Redis configuration
type RedisConfig struct {
	Host     string
	Port     string
	Password string
	DB       int
}

// JWTConfig holds JWT configuration
type JWTConfig struct {
	Secret          string
	ExpirationHours int
}

// UploadConfig holds file upload configuration
type UploadConfig struct {
	MaxSize              int64
	UploadDir            string
	AllowedVideoFormats  []string
	AllowedDocFormats    []string
	AllowedImageFormats  []string
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

// CORSConfig holds CORS configuration
type CORSConfig struct {
	AllowedOrigins   []string
	AllowedMethods   []string
	AllowedHeaders   []string
	AllowCredentials bool
}

// ServerConfig holds server configuration
type ServerConfig struct {
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
	IdleTimeout  time.Duration
}

// EmailConfig holds email configuration
type EmailConfig struct {
	SMTPHost     string
	SMTPPort     int
	SMTPUser     string
	SMTPPassword string
	FromEmail    string
	FromName     string
}

func LoadStorageConfig() StorageConfig {
	storageType := getEnv("STORAGE_TYPE", "local")
	
	return StorageConfig{
		Type:           storageType,
		LocalBasePath:  getEnv("STORAGE_LOCAL_PATH", "./uploads"),
		MinIOEndpoint:  getEnv("MINIO_ENDPOINT", "localhost:9000"),
		MinIOAccessKey: getEnv("MINIO_ACCESS_KEY", "minioadmin"),
		MinIOSecretKey: getEnv("MINIO_SECRET_KEY", "minioadmin123"),
		MinIOBucket:    getEnv("MINIO_BUCKET", "lms-files"),
		MinIOUseSSL:    getEnv("MINIO_USE_SSL", "false") == "true",
	}
}

// Load loads configuration from environment variables
func Load() (*Config, error) {
	// Load .env file if exists (for development)
	_ = godotenv.Load()

	cfg := &Config{
		App: AppConfig{
			Name:      getEnv("APP_NAME", "LMS Service"),
			Env:       getEnv("APP_ENV", "development"),
			Port:      getEnv("APP_PORT", "8081"),
			Version:   getEnv("VERSION", "1.0.0"),
			BuildDate: getEnv("BUILD_DATE", time.Now().Format(time.RFC3339)),
			LogLevel:  getEnv("LOG_LEVEL", "INFO"),
			LogFormat: getEnv("LOG_FORMAT", "json"),
		},

		Database: DatabaseConfig{
			Host:            getEnv("DB_HOST", "localhost"),
			Port:            getEnv("DB_PORT", "5434"),
			User:            getEnv("DB_USER", "lms_user"),
			Password:        getEnv("DB_PASSWORD", "lms_password"),
			Name:            getEnv("DB_NAME", "lms_db"),
			SSLMode:         getEnv("DB_SSL_MODE", "disable"),
			MaxOpenConns:    getEnvAsInt("DB_MAX_OPEN_CONNS", 25),
			MaxIdleConns:    getEnvAsInt("DB_MAX_IDLE_CONNS", 5),
			ConnMaxLifetime: getEnvAsDuration("DB_CONN_MAX_LIFETIME", 5*time.Minute),
		},

		Redis: RedisConfig{
			Host:     getEnv("REDIS_HOST", "localhost"),
			Port:     getEnv("REDIS_PORT", "6379"),
			Password: getEnv("REDIS_PASSWORD", ""),
			DB:       getEnvAsInt("REDIS_DB", 0),
		},

		JWT: JWTConfig{
			Secret:          getEnv("JWT_SECRET", "very_secret_key_change_me_please"),
			ExpirationHours: getEnvAsInt("JWT_EXPIRATION_HOURS", 1),
		},

		Upload: UploadConfig{
			MaxSize:   getEnvAsInt64("UPLOAD_MAX_SIZE", 104857600), // 100MB
			UploadDir: getEnv("UPLOAD_DIR", "/app/uploads"),
			AllowedVideoFormats: getEnvAsSlice("ALLOWED_VIDEO_FORMATS", 
				[]string{"mp4", "avi", "mov", "mkv", "webm"}),
			AllowedDocFormats: getEnvAsSlice("ALLOWED_DOCUMENT_FORMATS",
				[]string{"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx"}),
			AllowedImageFormats: getEnvAsSlice("ALLOWED_IMAGE_FORMATS",
				[]string{"jpg", "jpeg", "png", "gif", "webp"}),
		},

		CORS: CORSConfig{
			// Thêm tất cả origins giống như Java config
			AllowedOrigins: getEnvAsSlice("CORS_ALLOWED_ORIGINS",
				[]string{
					"http://localhost:3000",
					"http://frontend:8080",
					"http://localhost:8080",
					"http://backend:8080",
					"https://bdc.hpcc.vn",
				}),
			AllowedMethods: []string{"GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"},
			AllowedHeaders: []string{
				"Origin", "Content-Type", "Accept", "Authorization",
				"X-Request-ID", "X-Requested-With",
			},
			AllowCredentials: true,
		},

		Server: ServerConfig{
			ReadTimeout:  getEnvAsDuration("SERVER_READ_TIMEOUT", 15*time.Second),
			WriteTimeout: getEnvAsDuration("SERVER_WRITE_TIMEOUT", 15*time.Second),
			IdleTimeout:  getEnvAsDuration("SERVER_IDLE_TIMEOUT", 60*time.Second),
		},

		Email: EmailConfig{
			SMTPHost:     getEnv("SMTP_HOST", "smtp.gmail.com"),
			SMTPPort:     getEnvAsInt("SMTP_PORT", 587),
			SMTPUser:     getEnv("SMTP_USER", ""),
			SMTPPassword: getEnv("SMTP_PASSWORD", ""),
			FromEmail:    getEnv("EMAIL_FROM", "noreply@lms.com"),
			FromName:     getEnv("EMAIL_FROM_NAME", "LMS System"),
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

// IsDevelopment returns true if running in development mode
func (c *Config) IsDevelopment() bool {
	return c.App.Env == "development"
}

// IsProduction returns true if running in production mode
func (c *Config) IsProduction() bool {
	return c.App.Env == "production"
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

func getEnvAsInt64(key string, defaultValue int64) int64 {
	valueStr := getEnv(key, "")
	if value, err := strconv.ParseInt(valueStr, 10, 64); err == nil {
		return value
	}
	return defaultValue
}

func getEnvAsBool(key string, defaultValue bool) bool {
	valueStr := getEnv(key, "")
	if value, err := strconv.ParseBool(valueStr); err == nil {
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

func getEnvAsSlice(key string, defaultValue []string) []string {
	valueStr := getEnv(key, "")
	if valueStr == "" {
		return defaultValue
	}
	return strings.Split(valueStr, ",")
}