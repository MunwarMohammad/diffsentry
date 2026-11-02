from datetime import timedelta

from fastapi.testclient import TestClient

from reviewer.database import session
from reviewer.models import Job, Review, now
from services.webhook.main import app


def test_queue_metrics_report_failure_and_overdue_work():
    with session() as db:
        review = Review(repo="demo/example", number=1, head_sha="a" * 40, installation_id=1)
        db.add(review)
        db.flush()
        db.add(Job(review_id=review.id, kind="analyze", status="failed"))
        db.add(
            Job(
                review_id=review.id,
                kind="learn",
                status="pending",
                available_at=now() - timedelta(minutes=10),
            )
        )
        db.commit()
    with TestClient(app) as client:
        response = client.get("/queue-metrics")
        assert response.status_code == 200
        assert 'diffsentry_jobs{kind="analyze",status="failed"} 1.0' in response.text
        overdue = next(
            line
            for line in response.text.splitlines()
            if line.startswith("diffsentry_overdue_seconds ")
        )
        assert float(overdue.split()[1]) >= 600


def test_failed_job_retry_clears_delivery_generation(auth):
    with session() as db:
        review = Review(repo="demo/example", number=1, head_sha="a" * 40, installation_id=1)
        db.add(review)
        db.flush()
        job = Job(
            review_id=review.id, kind="analyze", status="failed", attempts=6, lease_token="obsolete"
        )
        db.add(job)
        db.commit()
        job_id = job.id
    with TestClient(app) as client:
        assert client.post(f"/jobs/{job_id}/retry").status_code == 401
        assert client.post(f"/jobs/{job_id}/retry", headers=auth).status_code == 200
        assert client.post(f"/jobs/{job_id}/retry", headers=auth).status_code == 409
    with session() as db:
        job = db.get(Job, job_id)
        assert job.status == "pending" and job.attempts == 0 and job.lease_token is None
