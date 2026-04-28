from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    app_port: int = 8000
    log_level: str = "INFO"

    # ── AI PostgreSQL ──────────────────────────────────────────────────────────
    ai_db_host: str = "postgres-ai"
    ai_db_port: int = 5432
    ai_db_user: str = "ai_user"
    ai_db_password: str = "ai_password"
    ai_db_name: str = "ai_db"
    ai_db_ssl: str = "require"  # None | disable | require | verify-ca | verify-full
    ai_db_min_connections: int = 5
    ai_db_max_connections: int = 20

    # ── Qdrant Vector Store ────────────────────────────────────────────────────
    qdrant_url: str | None = None  # Full URL: https://...:6333
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_prefer_grpc: bool = True
    qdrant_api_key: str = ""

    # ── Neo4j Knowledge Graph ──────────────────────────────────────────────────
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j_password"
    neo4j_enabled: bool = True

    # Feature flags
    use_qdrant: bool = True

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
    minio_use_ssl: bool = True

    # Groq LLM
    groq_api_key: str = ""
    chat_model: str = "llama-3.1-8b-instant"
    quiz_model: str = "llama-3.3-70b-versatile"

    # Google Gemini
    gemini_api_key: str = ""

    # Anthropic Claude
    anthropic_api_key: str = ""

    # Embedding
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimensions: int = 1024
    vlm_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    vlm_enabled: bool = True
    embedding_prefix_mode: str = "bge"

    # Reranker
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    use_reranker: bool = True
    rerank_fetch_k: int = 15

    # RAG
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k_chunks: int = 3
    use_native_multilingual: bool = True

    # Hierarchical chunking (parent-child). Children are embedded and indexed
    # in Qdrant; parents are stored in PG only and used to hydrate retrieved
    # children with wider context for the LLM.
    use_hierarchical_chunks: bool = True
    parent_chunk_max_chars: int = 6000

    # Kafka worker tuning
    reindex_batch_size: int = 5

    # Internal
    lms_service_url: str = "http://lms-service:8081"
    ai_service_secret: str = "ai-service-secret-change-me"

    ai_key_encryption_secret: str = ""
    llm_bootstrap_on_startup: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def ai_database_url(self) -> str:
        url = (
            f"postgresql+asyncpg://{self.ai_db_user}:{self.ai_db_password}"
            f"@{self.ai_db_host}:{self.ai_db_port}/{self.ai_db_name}"
        )
        if self.ai_db_ssl and self.ai_db_ssl != "disable":
            url += f"?ssl={self.ai_db_ssl}"
        return url

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return (
                f"redis://:{self.redis_password}"
                f"@{self.redis_host}:{self.redis_port}/{self.redis_db}"
            )
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
