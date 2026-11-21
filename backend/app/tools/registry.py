"""Registo de ferramentas em allowlist. So as ferramentas registadas existem para os agentes."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from backend.app.tools import handlers as h
from backend.app.tools import schemas as s

ALL_ROLES = frozenset({"requester", "reviewer", "admin"})


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    mutating: bool
    allowed_agents: frozenset[str]
    handler: Callable[[Any, BaseModel], dict] = field(compare=False, repr=False)
    allowed_roles: frozenset[str] = ALL_ROLES


def _build_registry() -> dict[str, ToolSpec]:
    specs = [
        ToolSpec(
            "search_tickets",
            "Pesquisa tickets do tenant (resumos, sem corpo).",
            s.SearchTicketsIn,
            s.SearchTicketsOut,
            False,
            frozenset({"triage", "knowledge_retrieval"}),
            h.search_tickets,
        ),
        ToolSpec(
            "get_ticket",
            "Devolve um ticket do tenant. Conteudo do ticket e nao confiavel.",
            s.GetTicketIn,
            s.TicketDetail,
            False,
            frozenset({"triage", "reporting"}),
            h.get_ticket,
        ),
        ToolSpec(
            "search_procedures",
            "Pesquisa procedimentos internos do tenant.",
            s.SearchProceduresIn,
            s.SearchProceduresOut,
            False,
            frozenset({"knowledge_retrieval"}),
            h.search_procedures,
        ),
        ToolSpec(
            "draft_reply",
            "Cria um rascunho de resposta com citacoes a procedimentos existentes (sem envio).",
            s.DraftReplyIn,
            s.DraftOut,
            False,
            frozenset({"reporting"}),
            h.draft_reply,
        ),
        ToolSpec(
            "propose_ticket_status",
            "Propoe mudar o estado de um ticket. Mutavel: exige aprovacao humana.",
            s.ProposeTicketStatusIn,
            s.ProposalOut,
            True,
            frozenset({"triage"}),
            h.propose_ticket_status,
        ),
        ToolSpec(
            "propose_account_action",
            "Propoe reset de MFA, suspensao ou reativacao de conta. Mutavel: exige aprovacao.",
            s.ProposeAccountActionIn,
            s.ProposalOut,
            True,
            frozenset({"triage"}),
            h.propose_account_action,
        ),
    ]
    return {spec.name: spec for spec in specs}


REGISTRY: dict[str, ToolSpec] = _build_registry()


def agent_tools() -> dict[str, tuple[str, ...]]:
    """Mapa agente -> ferramentas permitidas, derivado do registo (fonte unica de verdade)."""
    out: dict[str, list[str]] = {}
    for spec in REGISTRY.values():
        for agent in spec.allowed_agents:
            out.setdefault(agent, []).append(spec.name)
    return {agent: tuple(sorted(names)) for agent, names in sorted(out.items())}


def registry_fingerprint() -> str:
    """Impressao digital do registo (nomes, flags e agentes). Util para detetar alteracoes."""
    parts = [
        f"{spec.name}:{int(spec.mutating)}:{','.join(sorted(spec.allowed_agents))}"
        for spec in sorted(REGISTRY.values(), key=lambda x: x.name)
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
