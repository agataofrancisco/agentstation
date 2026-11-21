"""Demonstra que um no com interrupt() e reexecutado desde o inicio ao retomar (D4)."""

from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class S(TypedDict, total=False):
    calls: list[str]
    answer: str


def _gate(state: S) -> dict:
    # Efeito de contagem: se o no for reexecutado, esta linha corre outra vez.
    calls = [*state.get("calls", []), "gate"]
    answer = interrupt({"question": "aprovar?"})
    return {"calls": calls, "answer": answer}


def build():
    b = StateGraph(S)
    b.add_node("gate", _gate)
    b.add_edge(START, "gate")
    b.add_edge("gate", END)
    return b.compile(checkpointer=MemorySaver())


def test_node_with_interrupt_runs_again_on_resume():
    graph = build()
    cfg = {"configurable": {"thread_id": "t1"}}
    first = graph.invoke({"calls": []}, cfg)
    assert "__interrupt__" in first
    assert graph.get_state(cfg).values.get("calls") in (None, [])  # ainda nao escrito

    out = graph.invoke(Command(resume="sim"), cfg)
    assert out["answer"] == "sim"
    assert out["calls"] == ["gate"], "o no corre de novo, mas so a primeira linha tem efeito util"


def test_side_effect_before_interrupt_repeats_on_resume():
    counter = {"n": 0}

    def gate(state: S) -> dict:
        counter["n"] += 1  # efeito que NAO devia estar antes do interrupt
        return {"answer": interrupt("ok?")}

    b = StateGraph(S)
    b.add_node("gate", gate)
    b.add_edge(START, "gate")
    b.add_edge("gate", END)
    graph = b.compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t2"}}
    graph.invoke({}, cfg)
    graph.invoke(Command(resume="x"), cfg)
    assert counter["n"] == 2
