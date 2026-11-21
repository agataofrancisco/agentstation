"""Configuracao da aplicacao. Lida apenas de variaveis de ambiente (nunca de ficheiros .env)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    app_env: str = "dev"
    demo_mode: bool = True

    database_url: str = "sqlite:///data/runtime/agentstation.db"
    checkpoint_url: str = "sqlite:///data/runtime/checkpoints.db"

    celery_broker_url: str = "filesystem://"
    celery_eager: bool = False

    jwt_secret: str = "demo-only-insecure-secret-change-me"
    jwt_ttl_minutes: int = Field(default=120, gt=0)

    llm_provider: Literal["auto", "fake", "openai"] = "auto"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr | None = None
    llm_model: str = "gpt-4o-mini"
    llm_timeout_s: float = Field(default=30.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)
    llm_price_in_per_1k: float = Field(default=0.00015, ge=0)
    llm_price_out_per_1k: float = Field(default=0.0006, ge=0)
    fake_cost_per_call_usd: float = Field(default=0.001, ge=0)

    max_iterations: int = Field(default=12, gt=0)
    max_tool_calls: int = Field(default=20, gt=0)
    max_seconds: float = Field(default=120.0, gt=0)
    max_tokens: int = Field(default=50_000, gt=0)
    max_cost_usd: float = Field(default=0.5, gt=0)

    memory_ttl_days: int = Field(default=30, gt=0)
    chroma_path: str = "data/runtime/chroma"
    worker_heartbeat_ttl_s: float = Field(default=30.0, gt=0)

    # So para testes de recuperacao: termina o processo ao entrar neste no.
    crash_at_node: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
