"""Database outbox + bounded retries. Queue deliveries may repeat; handlers are idempotent."""

from datetime import timedelta

import httpx
from celery import Celery
from sqlalchemy import select

from reviewer.api import headers
from reviewer.config import get_settings
from reviewer.database import session
from reviewer.models import Job, now

settings = get_settings()
app = Celery("pr-reviewer", broker=settings.redis_url)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_soft_time_limit=540,
    task_time_limit=570,
    broker_transport_options={"visibility_timeout": 900},
    beat_schedule={"outbox": {"task": "dispatch", "schedule": 10.0}},
)


@app.task(name="dispatch")
def dispatch():
    with session() as db:
        jobs = db.scalars(
            select(Job)
            .where(Job.status.in_(["pending", "running"]), Job.available_at <= now())
            .limit(50)
            .with_for_update(skip_locked=True)
        ).all()
        for job in jobs:
            if job.attempts >= 6:
                job.status = "failed"
                job.last_error = job.last_error or "WorkerLeaseExpired"
                continue
            # Publish before committing lease: a crash can duplicate a job, but cannot lose it.
            app.send_task(
                "process_job", args=[job.id], queue="learning" if job.kind == "learn" else "reviews"
            )
            job.status = "pending"
            job.available_at = now() + timedelta(seconds=60)
        db.commit()
    return len(jobs)


@app.task(name="process_job")
def process_job(job_id):
    with session() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job is None or job.status in {"done", "failed"}:
            return
        available = job.available_at
        if available.tzinfo is None:
            available = available.replace(tzinfo=now().tzinfo)
        if job.status == "running" and available > now():
            return
        job.status = "running"
        job.attempts += 1
        job.available_at = now() + timedelta(seconds=600)
        kind, review_id = job.kind, job.review_id
        db.commit()
    error = None
    try:
        endpoint = (
            f"{settings.learner_url}/learn"
            if kind == "learn"
            else f"{settings.orchestrator_url}/analyze"
        )
        with httpx.Client(timeout=480) as client:
            response = client.post(endpoint, json={"review_id": review_id}, headers=headers())
            response.raise_for_status()
    except Exception as exc:
        # Avoid persisting provider payloads or secrets in logs/status APIs.
        error = type(exc).__name__
    with session() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        job.last_error = error
        job.status = "done" if error is None else ("failed" if job.attempts >= 6 else "pending")
        job.available_at = now() + timedelta(seconds=min(300, 10 * 2**job.attempts))
        db.commit()
