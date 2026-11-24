"""Ao arrancar o worker: batimento para o /health e reenfileiramento de tarefas nao concluidas.

O reenfileiramento e a rede de seguranca independente do broker: a verdade esta na base de dados
e no checkpoint. Corre o trabalho de forma idempotente (run_task_job retoma do checkpoint).
"""

from celery.signals import worker_ready

from backend.app.workers.heartbeat import start_heartbeat_thread
from backend.app.workers.runtime import current


@worker_ready.connect
def _on_worker_ready(sender=None, **kwargs):
    rt = current()
    start_heartbeat_thread(rt.deps.session_factory)
    from backend.app.workers.jobs import requeue_unfinished

    if rt.settings.requeue_on_start:
        requeue_unfinished(rt)
