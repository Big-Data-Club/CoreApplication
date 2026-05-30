package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/joho/godotenv"
)

// Config holds all configuration for the lab service.
type Config struct {
	App      AppConfig
	Database DatabaseConfig
	Redis    RedisConfig
	JWT      JWTConfig
	CORS     CORSConfig
	Server   ServerConfig
	Storage  StorageConfig
	K8s      K8sConfig
	SLURM    SLURMConfig
	Kafka    KafkaConfig
}

type AppConfig struct {
	Name    string
	Env     string
	Port    string
	Version string
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
	Secret          string
	ExpirationHours int
}

type CORSConfig struct {
	AllowedOrigins   []string
	AllowedMethods   []string
	AllowedHeaders   []string
	AllowCredentials bool
}

type ServerConfig struct {
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
	IdleTimeout  time.Duration
}

type StorageConfig struct {
	Type          string
	LocalBasePath string
	MinIOEndpoint string
	MinIOAccessKey string
	MinIOSecretKey string
	MinIOBucket   string
	MinIOUseSSL   bool
}

type K8sConfig struct {
	InCluster     bool
	Kubeconfig    string
	Namespace     string
	DefaultImage  string
	DefaultCPU    string
	DefaultMemory string
	MaxCPU        string
	MaxMemory     string
	IdleTimeout   time.Duration
	MaxSessionDur time.Duration
	StorageClass  string
	PVCSize       string
}

type SLURMConfig struct {
	Enabled          bool
	RestAPIURL       string
	AuthToken        string
	DefaultPartition string
	DefaultAccount   string
	ScratchDir       string
}

type KafkaConfig struct {
	Brokers string
}

func LoadStorageConfig() StorageConfig {
	return StorageConfig{
		Type:          getEnv("STORAGE_TYPE", "minio"),
		LocalBasePath: getEnv("STORAGE_LOCAL_PATH", "./uploads"),
		MinIOEndpoint: getEnv("MINIO_ENDPOINT", "minio:9000"),
		MinIOAccessKey: getEnv("MINIO_ACCESS_KEY", "minioadmin"),
		MinIOSecretKey: getEnv("MINIO_SECRET_KEY", "minioadmin123"),
		MinIOBucket:   getEnv("MINIO_BUCKET", "lab-files"),
		MinIOUseSSL:   getEnv("MINIO_USE_SSL", "false") == "true",
	}
}

// Load loads configuration from environment variables.
func Load() (*Config, error) {
	_ = godotenv.Load()

	cfg := &Config{
		App: AppConfig{
			Name:    getEnv("APP_NAME", "Lab Service"),
			Env:     getEnv("APP_ENV", "development"),
			Port:    getEnv("APP_PORT", "8082"),
			Version: getEnv("VERSION", "1.0.0"),
		},
		Database: DatabaseConfig{
			Host:            getEnv("DB_HOST", "localhost"),
			Port:            getEnv("DB_PORT", "5436"),
			User:            getEnv("DB_USER", "lab_user"),
			Password:        getEnv("DB_PASSWORD", "lab_password"),
			Name:            getEnv("DB_NAME", "lab_db"),
			SSLMode:         getEnv("DB_SSL_MODE", "disable"),
			MaxOpenConns:    getEnvAsInt("DB_MAX_OPEN_CONNS", 50),
			MaxIdleConns:    getEnvAsInt("DB_MAX_IDLE_CONNS", 10),
			ConnMaxLifetime: getEnvAsDuration("DB_CONN_MAX_LIFETIME", 30*time.Minute),
			ConnMaxIdleTime: getEnvAsDuration("DB_CONN_MAX_IDLE_TIME", 5*time.Minute),
		},
		Redis: RedisConfig{
			Host:         getEnv("REDIS_HOST", "localhost"),
			Port:         getEnv("REDIS_PORT", "6379"),
			Password:     getEnv("REDIS_PASSWORD", ""),
			DB:           getEnvAsInt("REDIS_DB", 2),
			PoolSize:     getEnvAsInt("REDIS_POOL_SIZE", 50),
			MinIdleConns: getEnvAsInt("REDIS_MIN_IDLE_CONNS", 10),
			DialTimeout:  getEnvAsDuration("REDIS_DIAL_TIMEOUT", 3*time.Second),
			ReadTimeout:  getEnvAsDuration("REDIS_READ_TIMEOUT", 500*time.Millisecond),
			WriteTimeout: getEnvAsDuration("REDIS_WRITE_TIMEOUT", 500*time.Millisecond),
			PoolTimeout:  getEnvAsDuration("REDIS_POOL_TIMEOUT", 1*time.Second),
		},
		JWT: JWTConfig{
			Secret:          getEnv("JWT_SECRET", "very_secret_key_change_me_please"),
			ExpirationHours: getEnvAsInt("JWT_EXPIRATION_HOURS", 1),
		},
		CORS: CORSConfig{
			AllowedOrigins: getEnvAsSlice("CORS_ALLOWED_ORIGINS", []string{
				"http://localhost:3000",
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
			ReadTimeout:  getEnvAsDuration("SERVER_READ_TIMEOUT", 10*time.Minute),
			WriteTimeout: getEnvAsDuration("SERVER_WRITE_TIMEOUT", 10*time.Minute),
			IdleTimeout:  getEnvAsDuration("SERVER_IDLE_TIMEOUT", 600*time.Second),
		},
		Storage: LoadStorageConfig(),
		K8s: K8sConfig{
			InCluster:     getEnvAsBool("K8S_IN_CLUSTER", false),
			Kubeconfig:    getEnv("K8S_KUBECONFIG", ""),
			Namespace:     getEnv("K8S_NAMESPACE", "lab-sessions"),
			DefaultImage:  getEnv("K8S_DEFAULT_IMAGE", "ubuntu:22.04"),
			DefaultCPU:    getEnv("K8S_DEFAULT_CPU", "500m"),
			DefaultMemory: getEnv("K8S_DEFAULT_MEMORY", "512Mi"),
			MaxCPU:        getEnv("K8S_MAX_CPU", "4000m"),
			MaxMemory:     getEnv("K8S_MAX_MEMORY", "8Gi"),
			IdleTimeout:   getEnvAsDuration("K8S_IDLE_TIMEOUT", 5*time.Minute),
			MaxSessionDur: getEnvAsDuration("K8S_MAX_SESSION_DURATION", 4*time.Hour),
			StorageClass:  getEnv("K8S_STORAGE_CLASS", "standard"),
			PVCSize:       getEnv("K8S_PVC_SIZE", "1Gi"),
		},
		SLURM: SLURMConfig{
			Enabled:          getEnvAsBool("SLURM_ENABLED", false),
			RestAPIURL:       getEnv("SLURM_REST_URL", ""),
			AuthToken:        getEnv("SLURM_AUTH_TOKEN", ""),
			DefaultPartition: getEnv("SLURM_DEFAULT_PARTITION", "normal"),
			DefaultAccount:   getEnv("SLURM_DEFAULT_ACCOUNT", "students"),
			ScratchDir:       getEnv("SLURM_SCRATCH_DIR", "/scratch/lab-jobs"),
		},
		Kafka: KafkaConfig{
			Brokers: getEnv("KAFKA_BROKERS", "localhost:9092"),
		},
	}

	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	return cfg, nil
}

func (c *Config) Validate() error {
	if c.Database.Host == "" {
		return fmt.Errorf("database host is required")
	}
	if c.Database.Name == "" {
		return fmt.Errorf("database name is required")
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

func (c *Config) GetDSN() string {
	return fmt.Sprintf(
		"host=%s port=%s user=%s password=%s dbname=%s sslmode=%s",
		c.Database.Host, c.Database.Port, c.Database.User,
		c.Database.Password, c.Database.Name, c.Database.SSLMode,
	)
}

// ── Helpers ─────────────────────────────────────────────────────

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvAsInt(key string, defaultValue int) int {
	if v, err := strconv.Atoi(getEnv(key, "")); err == nil {
		return v
	}
	return defaultValue
}

func getEnvAsBool(key string, defaultValue bool) bool {
	if v, err := strconv.ParseBool(getEnv(key, "")); err == nil {
		return v
	}
	return defaultValue
}

func getEnvAsDuration(key string, defaultValue time.Duration) time.Duration {
	if v, err := time.ParseDuration(getEnv(key, "")); err == nil {
		return v
	}
	return defaultValue
}

func getEnvAsSlice(key string, defaultValue []string) []string {
	v := getEnv(key, "")
	if v == "" {
		return defaultValue
	}
	return strings.Split(v, ",")
}
