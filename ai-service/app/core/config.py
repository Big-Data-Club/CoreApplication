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

    # ── Agent Memory ───────────────────────────────────────────────────────────
    stm_overflow_threshold: int = 3000        # tokens before STM overflow warning
    ltm_min_score: float = 0.3                # minimum cosine similarity for LTM recall
    ltm_facts_min_score: float = 0.5          # minimum score for fact recall
    max_context_tokens: int = 4000            # total token budget for memory context
    consolidation_turn_interval: int = 5      # trigger consolidation every N turns
    
    # ── Loaded from memory_config.yaml ──
    stm_budget: int = 1000
    ltm_episodic_budget: int = 1500
    ltm_facts_budget: int = 1000
    user_profile_budget: int = 500
    memory_decay_half_life: float = 30.0
    consolidation_min_importance: float = 0.7

    # Internal
    lms_service_url: str = "http://lms-service:8081"
    personalize_service_url: str = "http://personalize-service:8082"
    ai_service_secret: str = "ai-service-secret-change-me"

    def __init__(self, **values):
        super().__init__(**values)
        self._load_memory_config()

    def _load_memory_config(self) -> None:
        import os
        config_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../../config/memory_config.yaml")
        )
        if not os.path.exists(config_path):
            config_path = "config/memory_config.yaml"
            
        if os.path.exists(config_path):
            try:
                import yaml
                with open(config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except Exception:
                data = {}
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        curr_sec = None
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            if line.endswith(":"):
                                curr_sec = line[:-1].strip()
                                continue
                            if ":" in line:
                                k, v = line.split(":", 1)
                                k, v = k.strip(), v.strip()
                                if curr_sec == "token_budgets":
                                    data.setdefault("token_budgets", {})[k] = v
                                elif curr_sec == "decay_rates":
                                    data.setdefault("decay_rates", {})[k] = v
                                elif curr_sec == "consolidation":
                                    data.setdefault("consolidation", {})[k] = v
                except Exception:
                    pass

            if data:
                tb = data.get("token_budgets") or {}
                if "stm" in tb: self.stm_budget = int(tb["stm"])
                if "ltm_episodic" in tb: self.ltm_episodic_budget = int(tb["ltm_episodic"])
                if "ltm_facts" in tb: self.ltm_facts_budget = int(tb["ltm_facts"])
                if "user_profile" in tb: self.user_profile_budget = int(tb["user_profile"])
                if "max_context_tokens" in tb: self.max_context_tokens = int(tb["max_context_tokens"])

                dr = data.get("decay_rates") or {}
                if "half_life_days" in dr: self.memory_decay_half_life = float(dr["half_life_days"])

                c = data.get("consolidation") or {}
                if "turn_interval" in c: self.consolidation_turn_interval = int(c["turn_interval"])
                if "min_importance_score" in c: self.consolidation_min_importance = float(c["min_importance_score"])

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
