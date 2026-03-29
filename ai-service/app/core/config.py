from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    app_port: int = 8000
    log_level: str = "INFO"

    # PostgreSQL
    db_host: str = "postgres-lms"
    db_port: int = 5432
    db_user: str = "lms_user"
    db_password: str = "lms_password"
    db_name: str = "lms_db"
    db_min_connections: int = 2
    db_max_connections: int = 10

    # Redis
    redis_host: str = "redis-lms"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 1

    # MinIO
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
    minio_bucket: str = "lms-files"
    minio_use_ssl: bool = False

    # ════════════════════════════════════════════
    # Groq — FREE tier, rất nhanh
    # ════════════════════════════════════════════
    groq_api_key: str = ""

    # llama-3.1-8b-instant  → 560 tok/s, rẻ nhất, dùng cho diagnosis
    # llama-3.3-70b-versatile → 280 tok/s, tốt hơn, dùng cho quiz gen
    chat_model: str = "llama-3.1-8b-instant"
    quiz_model: str = "llama-3.3-70b-versatile"
    vlm_model:  str = "meta-llama/llama-4-scout-17b-16e-instruct"

    # Embedding (FastEmbed - chạy local, không cần server)
    embedding_model: str = "nomic-ai/nomic-embed-text-v1.5"
    embedding_dimensions: int = 768

    # RAG
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k_chunks: int = 3

    # Celery
    celery_task_time_limit: int = 3600

    # Internal
    lms_service_url: str = "http://lms-backend:8081"
    ai_service_secret: str = "ai-service-secret-change-me"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()