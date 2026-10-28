from contextlib import contextmanager
from unittest.mock import patch

import httpx
import respx
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from reviewer.config import get_settings
from reviewer.database import session
from reviewer.models import Job, Pattern, Review
from services.learner.main import app as learner
from services.orchestrator.main import app as orchestrator
from services.publisher.main import app as publisher
from services.webhook.main import app as webhook


def create_review(event, auth):
    with TestClient(webhook) as client:
        response = client.post("/events", json=event, headers=auth)
        assert response.status_code == 202
        return response.json()["review_id"]


def test_dedup_and_durable_job(event, auth):
    review_id = create_review(event, auth)
    with TestClient(webhook) as client:
        assert client.post("/events", json=event, headers=auth).json()["status"] == "duplicate"
    with session() as db:
        assert db.scalar(select(func.count()).select_from(Review)) == 1
        assert db.scalar(select(func.count()).select_from(Job)) == 1
        assert db.scalar(select(Job)).review_id == review_id


def test_distinct_commit_and_merge_targets_exact_head(event, auth):
    create_review(event, auth)
    event["pull_request"]["head"]["sha"] = "b" * 40
    second = create_review(event, auth)
    event["action"] = "closed"
    event["pull_request"]["merged"] = True
    assert create_review(event, auth) == second
    with session() as db:
        jobs = db.scalars(select(Job).where(Job.kind == "learn")).all()
        assert len(jobs) == 1 and jobs[0].review_id == second


def test_authorization_allowlist_and_drafts(event, auth):
    with TestClient(webhook) as client:
        assert client.post("/events", json=event).status_code == 401
        event["repository"]["full_name"] = "other/repo"
        assert client.post("/events", json=event, headers=auth).status_code == 403
        event["repository"]["full_name"] = "demo/example"
        event["pull_request"]["draft"] = True
        assert client.post("/events", json=event, headers=auth).json()["status"] == "ignored"


@respx.mock
def test_analysis_and_idempotent_learning(event, auth):
    review_id = create_review(event, auth)
    route = respx.post("http://localhost:8003/post-review").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    with TestClient(orchestrator) as client:
        assert (
            client.post("/analyze", json={"review_id": review_id}, headers=auth).status_code == 200
        )
    assert route.called
    with session() as db:
        review = db.get(Review, review_id)
        assert review.status == "analyzed"
        assert len(review.findings) == 3
    with TestClient(publisher) as client:
        result = client.post("/post-review", json={"review_id": review_id}, headers=auth).json()
        assert result["status"] == "dry_run"
        assert "DEMO" in result["summary"]
    with TestClient(learner) as client:
        assert (
            client.post("/learn", json={"review_id": review_id}, headers=auth).json()["patterns"]
            == 3
        )
        assert (
            client.post("/learn", json={"review_id": review_id}, headers=auth).json()["status"]
            == "skipped"
        )
    with session() as db:
        assert [p.frequency for p in db.scalars(select(Pattern))] == [1, 1, 1]


@respx.mock
def test_publisher_failure_retains_analysis(event, auth):
    review_id = create_review(event, auth)
    respx.post("http://localhost:8003/post-review").mock(return_value=httpx.Response(503))
    with TestClient(orchestrator, raise_server_exceptions=False) as client:
        assert (
            client.post("/analyze", json={"review_id": review_id}, headers=auth).status_code == 500
        )
    with session() as db:
        assert db.get(Review, review_id).status == "analyzed"
    respx.post("http://localhost:8003/post-review").mock(
        return_value=httpx.Response(200, json={"status": "dry_run"})
    )
    with (
        patch(
            "services.orchestrator.main.review_files",
            side_effect=AssertionError("must reuse stored analysis"),
        ),
        TestClient(orchestrator) as client,
    ):
        assert (
            client.post("/analyze", json={"review_id": review_id}, headers=auth).status_code == 200
        )


def test_learning_waits_for_analysis(event, auth):
    review_id = create_review(event, auth)
    with TestClient(learner) as client:
        assert client.post("/learn", json={"review_id": review_id}, headers=auth).status_code == 503


def test_clean_review_is_published_and_marked_complete(event, auth):
    review_id = create_review(event, auth)
    with session() as db:
        review = db.get(Review, review_id)
        review.status = "analyzed"
        review.findings = []
        db.commit()
    get_settings().publish_reviews = True

    @contextmanager
    def fake_client(_):
        yield object()

    with (
        patch("services.publisher.main.github_client", fake_client),
        patch("services.publisher.main.publish", return_value="123") as publish,
        TestClient(publisher) as client,
    ):
        result = client.post("/post-review", json={"review_id": review_id}, headers=auth)
        assert result.json()["status"] == "published"
        assert "No actionable findings" in publish.call_args.args[2]
        assert publish.call_args.args[3] == []
        client.post("/post-review", json={"review_id": review_id}, headers=auth)
        assert publish.call_count == 1
