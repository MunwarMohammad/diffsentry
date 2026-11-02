"""Durable outbox with delivery generations, bounded retries and fenced completion."""

from datetime import timedelta

import httpx
from celery import Celery
from sqlalchemy import select

from reviewer.api import headers
from reviewer.config import get_settings
from reviewer.database import session
from reviewer.models import Job, now, uid

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


def aware(value):
    return value if value.tzinfo else value.replace(tzinfo=now().tzinfo)


@app.task(name="dispatch")
def dispatch():
    with session() as db:
        jobs = db.scalars(
            select(Job)
            .where(
                Job.status.in_(["pending", "queued", "running"]),
                Job.available_at <= now(),
            )
            .order_by(Job.available_at)
            .limit(50)
            .with_for_update(skip_locked=True)
        ).all()
        for job in jobs:
            if job.attempts >= 6:
                job.status, job.lease_token = "failed", None
                job.last_error = job.last_error or "WorkerLeaseExpired"
                continue
            job.lease_token = uid()
            job.status = "queued"
            job.available_at = now() + timedelta(seconds=60)
            # Broker publication precedes commit. Rollback leaves an obsolete token,
            # which the consumer rejects; the next dispatch safely tries again.
            app.send_task(
                "process_job",
                args=[job.id, job.lease_token],
                queue="learning" if job.kind == "learn" else "reviews",
            )
        db.commit()
    return len(jobs)


@app.task(name="process_job")
def process_job(job_id, delivery_token=None):
    with session() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job is None or job.status in {"done", "failed", "running"}:
            return
        if job.status == "queued":
            if delivery_token is None or delivery_token != job.lease_token:
                return
        elif delivery_token is not None or aware(job.available_at) > now():
            return
        if job.attempts >= 6:
            job.status = "failed"
            db.commit()
            return
        job.status = "running"
        job.attempts += 1
        job.lease_token = token = uid()
        job.available_at = now() + timedelta(seconds=600)
        kind, review_id = job.kind, job.review_id
        db.commit()
    error = None
    try:
        if kind == "archive":
            from reviewer.archive import archive_review

            archive_review(review_id)
        else:
            endpoint = (
                f"{settings.learner_url}/learn"
                if kind == "learn"
                else f"{settings.orchestrator_url}/analyze"
            )
            with httpx.Client(timeout=480) as client:
                response = client.post(endpoint, json={"review_id": review_id}, headers=headers())
                response.raise_for_status()
    except Exception as exc:
        error = type(exc).__name__
    with session() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job is None or job.status != "running" or job.lease_token != token:
            return  # An expired worker must never overwrite a newer attempt.
        job.last_error = error
        job.lease_token = None
        job.status = "done" if error is None else ("failed" if job.attempts >= 6 else "pending")
        job.available_at = now() + timedelta(seconds=min(300, 10 * 2**job.attempts))
        db.commit()
