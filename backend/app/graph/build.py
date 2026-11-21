"""Montagem do StateGraph: nos, arestas e encaminhamento condicional."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.app.graph.agent_node import make_agent_node
from backend.app.graph.control_nodes import (
    make_approval_gate,
    make_execute_action,
    make_finalize,
    make_supervisor,
    make_verifier,
    route_after_gate,
    route_after_verifier,
)
from backend.app.graph.runtime import GraphDeps, traced
from backend.app.graph.state import TaskState

AGENTS = ("triage", "knowledge_retrieval", "reporting")


def build_graph(deps: GraphDeps, checkpointer: Any):
    builder = StateGraph(TaskState)
    builder.add_node("supervisor", traced("supervisor", deps, make_supervisor(deps)))
    for name in AGENTS:
        builder.add_node(name, traced(name, deps, make_agent_node(name, deps)))
    builder.add_node("verifier", traced("verifier", deps, make_verifier(deps)))
    builder.add_node("approval_gate", traced("approval_gate", deps, make_approval_gate(deps)))
    builder.add_node("execute_action", traced("execute_action", deps, make_execute_action(deps)))
    builder.add_node("finalize", traced("finalize", deps, make_finalize(deps)))

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        lambda state: state["next"],
        {**{name: name for name in AGENTS}, "verifier": "verifier", "finalize": "finalize"},
    )
    for name in AGENTS:
        builder.add_edge(name, "supervisor")
    builder.add_conditional_edges(
        "verifier", route_after_verifier, {"approval_gate": "approval_gate", "finalize": "finalize"}
    )
    builder.add_conditional_edges(
        "approval_gate",
        route_after_gate,
        {"execute_action": "execute_action", "finalize": "finalize"},
    )
    builder.add_edge("execute_action", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)


def recursion_limit_for(deps: GraphDeps) -> int:
    # Segunda barreira (LangGraph): acima do limite de iteracoes logico, nunca o atinge primeiro.
    return deps.settings.max_iterations * 4 + 20
