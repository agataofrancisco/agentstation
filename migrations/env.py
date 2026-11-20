"""Ambiente Alembic. A URL vem de -x url=... ou da variavel DATABASE_URL."""

import os
from logging.config import fileConfig

from alembic import context

from backend.app.config import get_settings
from backend.app.store import models  # noqa: F401  (regista os modelos no metadata)
from backend.app.store.db import Base, make_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = context.get_x_argument(as_dictionary=True).get("url") or os.environ.get(
    "DATABASE_URL", get_settings().database_url
)
target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = make_engine(url)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
