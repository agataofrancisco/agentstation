"""Ligacao a base de dados da aplicacao (PostgreSQL em producao, SQLite em dev e testes)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def _prepare_sqlite_path(url: str) -> None:
    prefix = "sqlite:///"
    if url.startswith(prefix) and url != "sqlite:///:memory:":
        Path(url[len(prefix) :]).parent.mkdir(parents=True, exist_ok=True)


def make_engine(url: str) -> Engine:
    connect_args: dict = {}
    is_sqlite = url.startswith("sqlite")
    if is_sqlite:
        _prepare_sqlite_path(url)
        connect_args["check_same_thread"] = False
    engine = create_engine(url, connect_args=connect_args, future=True)
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _sqlite_fk(dbapi_conn, _record):  # pragma: no cover - configuracao de ligacao
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
