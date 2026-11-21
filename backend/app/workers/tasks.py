"""Tarefas Celery finas: delegam em jobs.py. Argumentos so identificadores."""

from backend.app.workers import jobs
from backend.app.workers.celery_app import celery_app


@celery_app.task(name="agentstation.run_task", acks_late=True)
def run_task(task_id: str) -> str:
    return jobs.run_task_job(task_id)


@celery_app.task(name="agentstation.resume_task", acks_late=True)
def resume_task(task_id: str, approval_id: str) -> str:
    return jobs.resume_task_job(task_id, approval_id)
