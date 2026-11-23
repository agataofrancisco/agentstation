"""Batimento do worker na base de dados (health usa-o para ver worker activo)."""

from __future__ import annotations

import os
import threading
import time

from sqlalchemy.orm import Session, sessionmaker

from backend.app.store.models import WorkerHeartbeat

WORKER_ID = f"worker-{os.getpid()}"


def beat(
    session_factory: sessionmaker, worker_id: str = WORKER_ID, now: float | None = None
) -> None:
    with session_factory() as s:
        row = s.get(WorkerHeartbeat, worker_id)
        if row is None:
            s.add(WorkerHeartbeat(worker_id=worker_id, last_seen=now or time.time()))
        else:
            row.last_seen = now or time.time()
        s.commit()


def start_heartbeat_thread(
    session_factory: sessionmaker, interval_s: float = 10.0
) -> threading.Event:
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            beat(session_factory)
            stop.wait(interval_s)

    threading.Thread(target=loop, name="heartbeat", daemon=True).start()
    return stop


def worker_alive(session: Session, ttl_s: float, now: float | None = None) -> bool:
    cutoff = (now or time.time()) - ttl_s
    return session.query(WorkerHeartbeat).filter(WorkerHeartbeat.last_seen >= cutoff).count() > 0
