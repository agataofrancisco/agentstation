"""Escolha do provider de LLM. Sem chave e com LLM_PROVIDER=auto usa o falso (DEMO_MODE)."""

from __future__ import annotations

from backend.app.agents.fake import FakeProvider
from backend.app.agents.llm import LLMError, LLMProvider, OpenAICompatibleProvider
from backend.app.config import Settings


def make_provider(settings: Settings) -> LLMProvider:
    choice = settings.llm_provider
    if choice == "fake" or (choice == "auto" and settings.llm_api_key is None):
        if choice == "auto" and not settings.demo_mode:
            raise LLMError("sem LLM_API_KEY e DEMO_MODE=false: nenhum provider disponivel")
        return FakeProvider(settings.fake_cost_per_call_usd)
    return OpenAICompatibleProvider(settings)
