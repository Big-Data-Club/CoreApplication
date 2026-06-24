from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    app_port: int = 8082
    log_level: str = "INFO"
    
    kafka_brokers: str = "kafka:9092"
    
    data_dir: str = "/app/data"
    
    ai_service_secret: str = "ai-service-secret-change-me"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
