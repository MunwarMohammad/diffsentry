import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select

from reviewer.archive import archive_review, enqueue_archive
from reviewer.config import get_settings
from reviewer.database import session
from reviewer.models import Job, Review
from reviewer.summary import summary


def completed_review():
    with session() as db:
        review = Review(
            repo="demo/example",
            number=1,
            head_sha="a" * 40,
            installation_id=1,
            status="dry_run",
            findings=[],
            warnings=[],
        )
        db.add(review)
        db.commit()
        return review.id


def test_archive_disabled_by_default():
    review_id = completed_review()
    with session() as db:
        enqueue_archive(db, db.get(Review, review_id))
        db.commit()
        assert db.scalar(select(Job)) is None


def test_archive_is_separate_idempotent_job():
    get_settings().reports_s3_bucket = "test-bucket"
    review_id = completed_review()
    with session() as db:
        review = db.get(Review, review_id)
        enqueue_archive(db, review)
        enqueue_archive(db, review)
        db.commit()
        assert len(db.scalars(select(Job)).all()) == 1
    client = Mock()
    with patch("reviewer.archive.boto3.client", return_value=client):
        uri = archive_review(review_id)
        assert archive_review(review_id) == uri
    assert uri.startswith("s3://test-bucket/diffsentry/demo/example/")
    assert client.put_object.call_count == 1
    payload = json.loads(client.put_object.call_args.kwargs["Body"])
    assert payload["head_sha"] == "a" * 40
    assert "installation_id" not in payload


def test_archive_failure_preserves_review_completion():
    get_settings().reports_s3_bucket = "test-bucket"
    review_id = completed_review()
    client = Mock()
    client.put_object.side_effect = RuntimeError("storage unavailable")
    with patch("reviewer.archive.boto3.client", return_value=client), pytest.raises(RuntimeError):
        archive_review(review_id)
    with session() as db:
        review = db.get(Review, review_id)
        assert review.status == "dry_run" and review.archive_uri is None


def test_summary_bounded_for_large_provider_output():
    finding = {"file": "x" * 500, "line": 1, "message": "m" * 1500, "severity": "warning"}
    text = summary(SimpleNamespace(head_sha="a" * 40, findings=[finding] * 50, warnings=[]))
    assert len(text) < 56000
    assert "truncated" in text
