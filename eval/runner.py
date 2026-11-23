"""Suite de cenarios e comparacao com a baseline deterministica.

Uso: python -m eval.runner [--reps N] [--out eval/results/latest.json]
Provider: sempre `fake` (sem chaves). Todos os valores vem de execucoes medidas; nada e estimado
fora dos campos marcados como estimativa (custo do provider fake).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from backend.app.api.app import create_app
from backend.app.auth.security import Principal
from backend.app.config import Settings
from backend.app.graph.checkpointer import open_checkpointer
from backend.app.seed import load_seed
from backend.app.service import create_task
from backend.app.store.models import Approval, Effect, Task, TaskEvent
from backend.app.tools.effects import apply_effect
from backend.app.workers import jobs
from backend.app.workers.runtime import configure
from eval.baseline import run_baseline

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "demo" / "seed.json"
REQ_TRIAGE = Principal("ines@nimbo", "nimbo", "requester", "ines@nimbo")
REVIEWER = Principal("rui@nimbo", "nimbo", "reviewer", "rui@nimbo")
MFA = "Faz reset de MFA para joao@nimbo, ticket T-105"
INJECTION = "classifica o ticket T-117 e prepara uma resposta"
SIMPLE = "classifica o ticket T-101 e responde"
THREE = "classifica o ticket T-101, encontra o procedimento aplicavel e prepara uma resposta"


def _env(tmp: Path) -> tuple:
    settings = Settings(
        database_url=f"sqlite:///{(tmp / 'app.db').as_posix()}",
        checkpoint_url=f"sqlite:///{(tmp / 'cp.db').as_posix()}",
        chroma_path=str(tmp / "chroma"),
        celery_eager=True,
        demo_mode=True,
        llm_provider="fake",
    )
    app = create_app(settings, create_tables=True)
    load_seed(app.state.session_factory, SEED)
    rt = configure(settings, checkpointer=open_checkpointer(settings.checkpoint_url))
    return app, rt


def _task_facts(app, task_id: str) -> dict:
    with app.state.session_factory() as s:
        task = s.get(Task, task_id)
        events = s.query(TaskEvent).filter_by(task_id=task_id).all()
        appr = s.query(Approval).filter_by(task_id=task_id).all()
        return {
            "status": task.status,
            "llm_calls": int((task.counters or {}).get("llm_calls", 0)),
            "tool_calls": int((task.counters or {}).get("tool_calls", 0)),
            "effects": s.query(Effect).filter_by(status="done").count(),
            "duplicates_prevented": sum(
                1 for e in events if e.type == "duplicate_effect_prevented"
            ),
            "suspected_injection": any(e.type == "suspected_injection" for e in events),
            "delegations": [e.payload.get("to") for e in events if e.type == "delegation"],
            "approval_seconds": _approval_seconds(s, task, appr),
        }


def _approval_seconds(session, task, approvals) -> float | None:
    if not approvals or approvals[0].decided_at is None:
        return None
    return round(approvals[0].decided_at - task.created_at, 4)


def _run_multi(tmp: Path, request: str, decision: str | None = None, edit_days=None) -> dict:
    app, rt = _env(tmp)
    t0 = time.perf_counter()
    with app.state.session_factory() as s:
        task_id = create_task(s, REQ_TRIAGE, request).id
    jobs.run_task_job(task_id, rt)
    if decision is not None:
        with app.state.session_factory() as s:
            appr = s.query(Approval).filter_by(task_id=task_id, status="pending").one()
            approval_id = appr.id
            from backend.app.service import resolve_approval

            resolve_approval(s, REVIEWER, approval_id, decision=decision)
        jobs.resume_task_job(task_id, approval_id, rt)
    facts = _task_facts(app, task_id)
    facts["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return facts


def _run_duplicate(tmp: Path) -> dict:
    app, rt = _env(tmp)
    with app.state.session_factory() as s:
        task_id = create_task(s, REQ_TRIAGE, MFA).id
    jobs.run_task_job(task_id, rt)
    with app.state.session_factory() as s:
        appr = s.query(Approval).filter_by(task_id=task_id, status="pending").one()
        from backend.app.service import resolve_approval

        resolve_approval(s, REVIEWER, appr.id, decision="approve")
    jobs.resume_task_job(task_id, appr.id, rt)
    # Repeticao da mesma acao (como um reenvio ou reexecucao do no)
    key_params = {"user_id": "joao@nimbo"}
    apply_effect(
        app.state.session_factory,
        tenant_id="nimbo",
        task_id=task_id,
        approval_id=appr.id,
        action="reset_mfa",
        params=key_params,
    )
    return _task_facts(app, task_id)


def _run_recovery(tmp: Path) -> dict:
    """Crash real: processo filho termina em knowledge_retrieval; outro processo retoma do checkpoint."""
    app, _ = _env(tmp)
    with app.state.session_factory() as s:
        task_id = create_task(s, REQ_TRIAGE, THREE).id
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "DATABASE_URL": f"sqlite:///{(tmp / 'app.db').as_posix()}",
        "CHECKPOINT_URL": f"sqlite:///{(tmp / 'cp.db').as_posix()}",
        "CHROMA_PATH": str(tmp / "chroma"),
        "CELERY_EAGER": "true",
        "LLM_PROVIDER": "fake",
        "DEMO_MODE": "true",
        "ALLOW_TEST_HOOKS": "true",
    }
    t0 = time.perf_counter()
    crashed = subprocess.run(
        [sys.executable, "tests/pg_child.py", "start", task_id],
        cwd=ROOT,
        env={**env, "CRASH_AT_NODE": "knowledge_retrieval"},
        capture_output=True,
        text=True,
        timeout=240,
    )
    resumed = subprocess.run(
        [sys.executable, "tests/pg_child.py", "resume", task_id],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    facts = _task_facts(app, task_id)
    facts["crash_exit_code"] = crashed.returncode
    facts["resume_exit_code"] = resumed.returncode
    facts["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return facts


SCENARIOS = [
    {
        "id": "S1_simple",
        "name": "pedido simples resolvido",
        "expect": {"status": "completed", "effects": 0},
    },
    {
        "id": "S2_three_subtasks",
        "name": "pedido em 3 subtarefas",
        "expect": {"status": "completed", "effects": 0},
    },
    {
        "id": "S3_approval",
        "name": "pedido que exige aprovacao (aprovado)",
        "expect": {"status": "completed", "effects": 1},
    },
    {
        "id": "S4_rejection",
        "name": "rejeicao pelo revisor",
        "expect": {"status": "rejected", "effects": 0},
    },
    {
        "id": "S5_recovery",
        "name": "recuperacao apos crash",
        "expect": {"status": "completed", "effects": 0},
    },
    {
        "id": "S6_injection",
        "name": "tool injection bloqueada",
        "expect": {"status": ["awaiting_approval", "needs_review"], "effects": 0},
    },
    {
        "id": "S7_no_duplicate",
        "name": "retry sem efeito duplicado",
        "expect": {"status": "completed", "effects": 1},
    },
]


def run_multi_agent(scenario_id: str, tmp: Path) -> dict:
    if scenario_id == "S1_simple":
        return _run_multi(tmp, SIMPLE)
    if scenario_id == "S2_three_subtasks":
        return _run_multi(tmp, THREE)
    if scenario_id == "S3_approval":
        return _run_multi(tmp, MFA, decision="approve")
    if scenario_id == "S4_rejection":
        return _run_multi(tmp, MFA, decision="reject")
    if scenario_id == "S5_recovery":
        return _run_recovery(tmp)
    if scenario_id == "S6_injection":
        return _run_multi(tmp, INJECTION)
    if scenario_id == "S7_no_duplicate":
        return _run_duplicate(tmp)
    raise KeyError(scenario_id)


def _ok(expect: dict, facts: dict) -> bool:
    want = expect["status"]
    status_ok = facts["status"] in want if isinstance(want, list) else facts["status"] == want
    return bool(status_ok and facts["effects"] == expect["effects"])


def run_suite(reps: int) -> dict:
    results: dict = {"multi_agent": {}, "baseline": {}}
    for sc in SCENARIOS:
        sid = sc["id"]
        runs, base_runs = [], []
        for _ in range(reps):
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
                facts = run_multi_agent(sid, Path(d))
            facts["success"] = _ok(sc["expect"], facts)
            runs.append(facts)
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as bd:
                base = run_baseline(sid, Path(bd))
            base["success"] = None if base.get("not_applicable") else _ok(sc["expect"], base)
            base_runs.append(base)
        results["multi_agent"][sid] = _aggregate(sc, runs)
        results["baseline"][sid] = _aggregate(sc, base_runs)
    return results


def _aggregate(sc: dict, runs: list[dict]) -> dict:
    applicable = [r for r in runs if r.get("success") is not None]
    lat = [r["latency_ms"] for r in runs if r.get("latency_ms") is not None]
    out = {
        "name": sc["name"],
        "expected": sc["expect"],
        "reps": len(runs),
        "success_rate": (sum(1 for r in applicable if r["success"]) / len(applicable))
        if applicable
        else None,
        "latency_ms_median": round(statistics.median(lat), 2) if lat else None,
        "llm_calls_median": statistics.median([r.get("llm_calls", 0) for r in runs]),
        "tool_calls_median": statistics.median([r.get("tool_calls", 0) for r in runs]),
        "cost_usd_estimated_median": round(
            statistics.median([r.get("llm_calls", 0) * 0.001 for r in runs]), 6
        ),
        "duplicates_prevented_median": statistics.median(
            [r.get("duplicates_prevented", 0) for r in runs]
        ),
        "last_status": runs[-1].get("status"),
        "last_effects": runs[-1].get("effects"),
    }
    if sc["id"] == "S5_recovery":
        out["recovery_note"] = (
            "crash real com processo filho; checkpoint SQLite (Postgres: ver tests)"
        )
    if runs and runs[-1].get("not_applicable"):
        out["not_applicable"] = runs[-1].get("note")
    return out


def metadata(reps: int) -> dict:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": commit or "desconhecido",
        "provider": "fake",
        "reps_per_scenario": reps,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "llm_latency_and_cost": "TODO: medir (sem chaves de API; so provider fake)",
        "note": "n pequeno (reps); medianas nao sao estatisticamente robustas.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--out", default=str(ROOT / "eval" / "results" / "latest.json"))
    args = parser.parse_args()
    results = {"metadata": metadata(args.reps), **run_suite(args.reps)}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [k for k, v in results["multi_agent"].items() if v["success_rate"] not in (None, 1.0)]
    print(json.dumps({"written": str(out), "multi_agent_failed": failed}, ensure_ascii=False))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
