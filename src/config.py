"""Application configuration via Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Supply Chain Agent Platform"
    environment: Literal["local", "staging", "production"] = "local"
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    # LLM
    openai_api_key: str | None = None
    default_model: str = "gpt-4o-mini"
    premium_model: str = "gpt-4o"
    router_complexity_threshold: float = 0.65

    # Infrastructure (optional — graceful degradation when unset)
    redis_url: str | None = "redis://localhost:6379/0"
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    kafka_bootstrap: str | None = "localhost:9092"
    kafka_topic: str = "agent.events"
    mlflow_tracking_uri: str | None = "http://localhost:5000"
    otel_exporter_endpoint: str | None = "http://localhost:4318"
    grpc_inventory_host: str = "localhost"
    grpc_inventory_port: int = 50051

    # Governance (reuses existing harness)
    judge_threshold: float = 0.6
    judge_seed: int = 7

    # Feature flags
    use_live_llm: bool = Field(default=False, description="Enable real LLM calls")
    enable_kafka: bool = False
    enable_mlflow: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
