"""Aplicacao Celery: so motor de execucao. O estado vive no checkpointer e na base de dados."""

import os

from celery import Celery

from backend.app.config import get_settings

_settings = get_settings()


def _broker_transport_options() -> dict:
    """Broker filesystem: produtor e consumidor partilham a mesma pasta (sem Redis)."""
    if _settings.celery_broker_url.startswith("filesystem") and _settings.celery_fs_dir:
        folder = os.path.abspath(_settings.celery_fs_dir)
        os.makedirs(folder, exist_ok=True)
        return {"data_folder_in": folder, "data_folder_out": folder, "store_processed": False}
    return {}


celery_app = Celery("agentstation", broker=_settings.celery_broker_url)
celery_app.conf.update(
    task_always_eager=_settings.celery_eager,
    task_eager_propagates=True,
    task_acks_late=True,  # o job so e confirmado depois de terminar
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    result_backend=None,
    task_ignore_result=True,
    broker_transport_options=_broker_transport_options(),
    imports=["backend.app.workers.tasks", "backend.app.workers.signals"],
)
