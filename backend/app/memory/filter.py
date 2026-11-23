"""Filtro de escrita da memoria: bloqueia segredos, dados pessoais e origem nao confiavel."""

from __future__ import annotations

import re
import unicodedata

SECRET = re.compile(
    r"\b(password|palavra[- ]?passe|senha|passwd|pwd|token|api[ _-]?key|segredo|secret)\b"
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)*")
IBAN = re.compile(r"\bPT\d{23}\b|\bIBAN\b", re.IGNORECASE)
NIF = re.compile(r"\b\d{9}\b")
PHONE = re.compile(r"\b9\d{8}\b")


def _norm(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    ).lower()


def write_decision(text: str, *, untrusted_origin: bool) -> tuple[bool, str | None]:
    """Devolve (permitido, motivo_se_bloqueado)."""
    if untrusted_origin:
        return False, "untrusted_origin"
    if not isinstance(text, str) or not text.strip():
        return False, "empty"
    normalized = _norm(text)
    if SECRET.search(normalized):
        return False, "secret"
    if EMAIL.search(text) or IBAN.search(text) or NIF.search(text) or PHONE.search(text):
        return False, "personal_data"
    return True, None
