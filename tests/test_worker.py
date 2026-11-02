from datetime import timedelta
from unittest.mock import patch

import respx
from sqlalchemy import select

from reviewer.database import session
from reviewer.models import Job, Review, now


def job():
    with session() as db:
        review = Review(repo="demo/example", number=1, head_sha="a" * 40, installation_id=1)
        db.add(review)
        db.flush()
        item = Job(review_id=review.id, kind="analyze")
        db.add(item)
        db.commit()
        return item.id


def test_outbox_broker_failure_keeps_job_pending():
    from reviewer.worker import app, dispatch

    job_id = job()
    with patch.object(app, "send_task", side_effect=ConnectionError("broker down")):
        import pytest

        with pytest.raises(ConnectionError):
            dispatch()
    with session() as db:
        assert db.get(Job, job_id).status == "pending"


@respx.mock
def test_failure_retry_and_success():
    from reviewer.worker import process_job, settings

    job_id = job()
    route = respx.post(f"{settings.orchestrator_url}/analyze").respond(503)
    process_job(job_id)
    with session() as db:
        item = db.get(Job, job_id)
        assert item.status == "pending" and item.attempts == 1
        assert item.last_error == "HTTPStatusError"
    make_due(job_id)
    route.respond(200, json={"status": "dry_run"})
    process_job(job_id)
    process_job(job_id)
    with session() as db:
        assert db.get(Job, job_id).status == "done"
    assert route.call_count == 2


def test_expired_worker_lease_recoverable():
    from reviewer.worker import app, dispatch

    job_id = job()
    with session() as db:
        item = db.get(Job, job_id)
        item.status = "running"
        item.available_at = now() - timedelta(minutes=1)
        db.commit()
    with patch.object(app, "send_task") as send:
        dispatch()
        assert send.call_count == 1
    with session() as db:
        assert db.get(Job, job_id).status == "queued"


@respx.mock
def test_bounded_retries():
    from reviewer.worker import process_job, settings

    job_id = job()
    respx.post(f"{settings.orchestrator_url}/analyze").respond(500)
    for _ in range(6):
        make_due(job_id)
        process_job(job_id)
    with session() as db:
        assert db.scalar(select(Job)).status == "failed"


def make_due(job_id):
    with session() as db:
        db.get(Job, job_id).available_at = now() - timedelta(seconds=1)
        db.commit()


@respx.mock
def test_duplicate_cannot_skip_retry_backoff():
    from reviewer.worker import process_job, settings

    job_id = job()
    route = respx.post(f"{settings.orchestrator_url}/analyze").respond(503)
    process_job(job_id)
    process_job(job_id)
    assert route.call_count == 1
    with session() as db:
        assert db.get(Job, job_id).attempts == 1


@respx.mock
def test_obsolete_delivery_token_is_rejected():
    from reviewer.worker import app, dispatch, process_job, settings

    job_id = job()
    with patch.object(app, "send_task") as send:
        dispatch()
        old_token = send.call_args.kwargs["args"][1]
        make_due(job_id)
        dispatch()
        new_token = send.call_args.kwargs["args"][1]
    route = respx.post(f"{settings.orchestrator_url}/analyze").respond(200, json={})
    process_job(job_id, old_token)
    assert route.call_count == 0
    process_job(job_id, new_token)
    assert route.call_count == 1


@respx.mock
def test_stale_worker_cannot_overwrite_new_attempt():
    import httpx

    from reviewer.worker import process_job, settings

    job_id = job()

    def newer_attempt(request):
        with session() as db:
            item = db.get(Job, job_id)
            item.lease_token = "new-owner"
            item.status = "running"
            db.commit()
        return httpx.Response(200, json={})

    respx.post(f"{settings.orchestrator_url}/analyze").mock(side_effect=newer_attempt)
    process_job(job_id)
    with session() as db:
        item = db.get(Job, job_id)
        assert item.status == "running"
        assert item.lease_token == "new-owner"
