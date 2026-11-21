"""Aplicacao Celery: so motor de execucao. O estado vive no checkpointer e na base de dados."""

from celery import Celery

from backend.app.config import get_settings

_settings = get_settings()

celery_app = Celery("agentstation", broker=_settings.celery_broker_url)
celery_app.conf.update(
    task_always_eager=_settings.celery_eager,
    task_eager_propagates=True,
    task_acks_late=True,  # o job so e confirmado depois de terminar: crash -> reentrega
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    imports=["backend.app.workers.tasks"],
)
