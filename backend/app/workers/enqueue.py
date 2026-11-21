"""Enfileiramento: em modo eager (testes/demo) executa na hora; senao envia para a fila Celery."""

from backend.app.workers import jobs
from backend.app.workers.runtime import current


def enqueue_run(task_id: str) -> None:
    if current().settings.celery_eager:
        jobs.run_task_job(task_id)
        return
    from backend.app.workers.tasks import run_task

    run_task.delay(task_id)


def enqueue_resume(task_id: str, approval_id: str) -> None:
    if current().settings.celery_eager:
        jobs.resume_task_job(task_id, approval_id)
        return
    from backend.app.workers.tasks import resume_task

    resume_task.delay(task_id, approval_id)
