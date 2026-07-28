from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    ai_service_secret: str = "ai-service-secret-change-me"
    personalize_service_url: str = "http://personalize-service:8082"
    kafka_brokers: str = "kafka:9092"
    recommendation_event_topic: str = "recommender.interactions.v1"
    # Can be rotated independently later; v1 falls back to the already-managed
    # internal secret so tracking tokens are valid across all service clients.
    tracking_secret: str = ""
    profile_cache_seconds: int = 300
    request_timeout_seconds: float = 1.5

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
