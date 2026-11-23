"""Achados de seguranca 1-3: fail-closed, segredo JWT obrigatorio, gancho de crash restrito."""

import itertools
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.graph.runtime import GraphDeps, traced

STRONG = "s" * 32


def test_demo_mode_is_off_by_default():
    assert Settings(jwt_secret=STRONG).demo_mode is False


def test_outside_demo_missing_secret_refuses_to_start():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(demo_mode=False, jwt_secret=None)


def test_outside_demo_short_secret_refuses_to_start():
    with pytest.raises(ValidationError, match="32"):
        Settings(demo_mode=False, jwt_secret="curto")


def test_outside_demo_strong_secret_is_accepted():
    s = Settings(demo_mode=False, jwt_secret=STRONG)
    assert s.jwt_secret == STRONG


def test_demo_generates_ephemeral_secret_per_process():
    a = Settings(demo_mode=True).jwt_secret
    b = Settings(demo_mode=True).jwt_secret
    assert a and b and len(a) >= 32 and len(b) >= 32
    assert a != b, "o segredo de demo nao pode ser fixo"


def test_public_default_secret_is_gone_from_code():
    source = (Path(__file__).resolve().parents[1] / "backend" / "app" / "config.py").read_text(
        encoding="utf-8"
    )
    assert "demo-only-insecure-secret-change-me" not in source


@pytest.mark.parametrize(
    "demo,allow,crash",
    list(itertools.product([False, True], [False, True], [None, "knowledge_retrieval"])),
)
def test_crash_hook_requires_demo_and_explicit_flag(demo, allow, crash):
    s = Settings(demo_mode=demo, allow_test_hooks=allow, crash_at_node=crash, jwt_secret=STRONG)
    expected = demo and allow and crash is not None
    assert s.crash_hook_enabled is expected


def test_crash_hook_is_off_by_default_even_with_node_set():
    s = Settings(crash_at_node="knowledge_retrieval", jwt_secret=STRONG)
    assert s.crash_hook_enabled is False


def test_traced_node_does_not_exit_when_hook_disabled(app, settings):
    """Com CRASH_AT_NODE mas sem o flag de teste, o no corre normalmente."""
    cfg = settings.model_copy(update={"crash_at_node": "triage", "allow_test_hooks": False})
    deps = GraphDeps(settings=cfg, session_factory=app.state.session_factory, llm=None)
    calls = []

    def fn(state):
        calls.append("ran")
        return {}

    node = traced("triage", deps, fn)
    from backend.app.auth.security import Principal
    from backend.app.service import create_task

    with app.state.session_factory() as db:
        task = create_task(db, Principal("ines@nimbo", "nimbo", "requester", "ines@nimbo"), "x")
    state = {"task_id": task.id, "tenant_id": "nimbo"}
    # Se o gancho estivesse activo, os._exit terminaria este processo de teste.
    assert node(state) == {}
    assert calls == ["ran"]
