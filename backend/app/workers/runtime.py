"""Runtime do processo (API ou worker): engine, grafo e checkpointer. Uma vez por processo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.agents.factory import make_provider
from backend.app.config import Settings, get_settings
from backend.app.graph.build import build_graph
from backend.app.graph.checkpointer import open_checkpointer
from backend.app.graph.runtime import GraphDeps
from backend.app.store.db import make_engine, make_session_factory


@dataclass
class Runtime:
    settings: Settings
    deps: GraphDeps
    graph: Any


_RUNTIME: Runtime | None = None


def configure(settings: Settings, *, checkpointer: Any | None = None) -> Runtime:
    global _RUNTIME
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    deps = GraphDeps(
        settings=settings,
        session_factory=session_factory,
        llm=make_provider(settings),
    )
    saver = checkpointer if checkpointer is not None else open_checkpointer(settings.checkpoint_url)
    _RUNTIME = Runtime(settings=settings, deps=deps, graph=build_graph(deps, saver))
    return _RUNTIME


def current() -> Runtime:
    if _RUNTIME is None:
        return configure(get_settings())
    return _RUNTIME
