"""Seed sintetico (idempotente): tenants, utilizadores, tickets e procedimentos.

Uso: python -m backend.app.seed [--path data/demo/seed.json]
Cada linha e gravada com merge pela chave primaria, por isso correr de novo nao duplica dados.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import sessionmaker

from backend.app.config import get_settings
from backend.app.store.db import make_engine, make_session_factory
from backend.app.store.models import Procedure, Tenant, Ticket, User

DEFAULT_PATH = Path("data/demo/seed.json")


def load_seed(session_factory: sessionmaker, path: Path = DEFAULT_PATH) -> dict[str, int]:
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    counts = {"tenants": 0, "users": 0, "tickets": 0, "procedures": 0}
    with session_factory() as session:
        for row in data.get("tenants", []):
            session.merge(Tenant(**row))
            counts["tenants"] += 1
        session.flush()  # tenants primeiro (FK sem relationships ORM)
        for row in data.get("users", []):
            session.merge(User(**row))
            counts["users"] += 1
        session.flush()
        for row in data.get("tickets", []):
            session.merge(Ticket(**row))
            counts["tickets"] += 1
        session.flush()
        for row in data.get("procedures", []):
            session.merge(Procedure(**row))
            counts["procedures"] += 1
        session.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Carrega o seed demo (idempotente).")
    parser.add_argument("--path", default=str(DEFAULT_PATH))
    args = parser.parse_args()
    settings = get_settings()
    engine = make_engine(settings.database_url)
    counts = load_seed(make_session_factory(engine), Path(args.path))
    print(json.dumps({"seeded": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
