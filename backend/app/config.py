"""Configuracao da aplicacao. Lida apenas de variaveis de ambiente (nunca de ficheiros .env)."""

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    app_env: str = "dev"
    # Fail-closed: por omissao NAO e demo. Demo activa-se explicitamente.
    demo_mode: bool = False

    database_url: str = "sqlite:///data/runtime/agentstation.db"
    checkpoint_url: str = "sqlite:///data/runtime/checkpoints.db"

    celery_broker_url: str = "filesystem://"
    celery_eager: bool = False
    # Pasta partilhada do broker filesystem (kombu). Sem Redis, para testes reais de worker.
    celery_fs_dir: str | None = None
    # Ao arrancar, reenfileira tarefas nao concluidas (rede de seguranca independente do broker).
    requeue_on_start: bool = True

    # Sem valor predefinido. Fora de demo: obrigatorio, >= 32 caracteres.
    # Em demo: gerado de forma efemera por processo (ver validador).
    jwt_secret: str | None = None
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
    # Origens do painel web (dev: frontend em 13100). Lista separada por virgulas.
    cors_origins: str = "http://127.0.0.1:13100,http://localhost:13100"
    chroma_path: str = "data/runtime/chroma"
    worker_heartbeat_ttl_s: float = Field(default=30.0, gt=0)

    # So para testes de recuperacao: termina o processo ao entrar neste no.
    crash_at_node: str | None = None
    # Gancho de teste: so tem efeito com ALLOW_TEST_HOOKS=true E DEMO_MODE=true.
    allow_test_hooks: bool = False

    @model_validator(mode="after")
    def _secure_defaults(self) -> "Settings":
        if self.demo_mode:
            if not self.jwt_secret:
                self.jwt_secret = secrets.token_urlsafe(32)  # efemero: muda a cada processo
        else:
            if not self.jwt_secret or len(self.jwt_secret) < 32:
                raise ValueError("fora de DEMO_MODE, JWT_SECRET e obrigatorio com >= 32 caracteres")
        return self

    @property
    def crash_hook_enabled(self) -> bool:
        return bool(self.crash_at_node and self.allow_test_hooks and self.demo_mode)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
