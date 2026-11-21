"""Deteccao heuristica de instrucoes escondidas em conteudo nao confiavel (tickets, procedimentos).

A deteccao NAO e a defesa principal: a defesa e a aprovacao obrigatoria e a autorizacao no backend.
Serve para registar `suspected_injection` e dar visibilidade ao revisor.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

PATTERNS: dict[str, re.Pattern[str]] = {
    "impersonates_admin": re.compile(r"\bcomo (administrador|admin|sistema)\b"),
    "auto_approve": re.compile(r"\baprova(r)? automaticamente\b"),
    "ignore_instructions": re.compile(
        r"\bignor[ae] (as |todas as |the |all |previous )?instrucoes"
        r"|\bignore (all |previous |the )?instructions\b"
    ),
    "skip_approval": re.compile(r"\bsem (necessidade de )?aprovacao\b|\bskip (the )?approval\b"),
    "tool_escalation": re.compile(
        r"\b(adiciona|regista) (a )?(nova )?ferramenta\b|\badd (a )?tool\b"
    ),
    "requester_change": re.compile(r"\bmuda (o )?requester\b|\bchange (the )?requester\b"),
    "prompt_markers": re.compile(r"</?system>|\[system\]|system prompt"),
}


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.lower()


def _strings(value: Any, depth: int = 0) -> list[str]:
    if depth > 6:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v, depth + 1)]
    if isinstance(value, list | tuple):
        return [s for v in value for s in _strings(v, depth + 1)]
    return []


def scan_untrusted(value: Any) -> list[str]:
    """Devolve os nomes dos padroes encontrados em qualquer string (vazia se limpo)."""
    hits: list[str] = []
    for text in _strings(value):
        normalized = _normalize(text)
        for name, pattern in PATTERNS.items():
            if pattern.search(normalized) and name not in hits:
                hits.append(name)
    return hits


def wrap_untrusted(text: str) -> str:
    """Delimita dados nao confiaveis antes de os entregar a um modelo."""
    safe = text.replace("</dados_nao_confiaveis>", "[removido]")
    return f"<dados_nao_confiaveis>\n{safe}\n</dados_nao_confiaveis>"
