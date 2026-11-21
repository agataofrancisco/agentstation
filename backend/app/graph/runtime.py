"""Dependencias do grafo e envolvimento dos nos (eventos, duracao, gancho de crash de teste)."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from backend.app.agents.llm import LLMProvider
from backend.app.config import Settings
from backend.app.graph.state import TaskState
from backend.app.store.events import add_event

CRASH_EXIT_CODE = 137


@dataclass
class GraphDeps:
    settings: Settings
    session_factory: sessionmaker
    llm: LLMProvider
    clock: Callable[[], float] = field(default=time.time)


def emit_for(
    session: Session,
    state: TaskState,
    node: str,
    agent: str | None = None,
) -> Callable[[str, dict[str, Any]], None]:
    """Cria o emissor de eventos ligado a tarefa, no; grava na mesma sessao do no."""

    def emit(type_: str, payload: dict[str, Any]) -> None:
        add_event(
            session,
            task_id=state["task_id"],
            tenant_id=state["tenant_id"],
            type_=type_,
            node=node,
            agent=agent,
            tool=payload.get("tool"),
            duration_ms=payload.get("duration_ms"),
            payload=payload,
        )

    return emit


def traced(
    name: str, deps: GraphDeps, fn: Callable[[TaskState], dict]
) -> Callable[[TaskState], dict]:
    """Regista node_started / node_finished. Nao capta excepcoes (GraphInterrupt tem de passar)."""

    def node(state: TaskState) -> dict:
        if deps.settings.crash_at_node == name:
            # Teste de recuperacao: sai do processo sem limpeza, como um crash real.
            os._exit(CRASH_EXIT_CODE)
        with deps.session_factory() as session:
            add_event(
                session,
                task_id=state["task_id"],
                tenant_id=state["tenant_id"],
                type_="node_started",
                node=name,
            )
        start = perf_counter()
        update = fn(state)
        duration = round((perf_counter() - start) * 1000, 3)
        with deps.session_factory() as session:
            add_event(
                session,
                task_id=state["task_id"],
                tenant_id=state["tenant_id"],
                type_="node_finished",
                node=name,
                duration_ms=duration,
            )
        return update

    node.__name__ = name
    return node
