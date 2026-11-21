"""Checkpointer do LangGraph: PostgreSQL ou SQLite. Thread = id da tarefa."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def open_checkpointer(url: str) -> Any:
    if url.startswith("postgresql"):
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row

        conn = psycopg.connect(url, autocommit=True, prepare_threshold=0, row_factory=dict_row)
        saver = PostgresSaver(conn)
        saver.setup()  # cria as tabelas do checkpointer (idempotente)
        return saver
    if url.startswith("sqlite:///"):
        from langgraph.checkpoint.sqlite import SqliteSaver

        path = Path(url[len("sqlite:///") :])
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        return SqliteSaver(conn)
    if url == "memory://":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    raise ValueError("CHECKPOINT_URL nao suportado")
