"""Optional report archival, independently retryable from GitHub publication."""

import json

import boto3
from botocore.config import Config
from sqlalchemy import select

from reviewer.config import get_settings
from reviewer.database import session
from reviewer.models import Job, Review


def enqueue_archive(db, review):
    if not get_settings().reports_s3_bucket or review.status not in {"published", "dry_run"}:
        return
    if not db.scalar(select(Job).where(Job.review_id == review.id, Job.kind == "archive")):
        db.add(Job(review_id=review.id, kind="archive"))


def archive_review(review_id):
    settings = get_settings()
    if not settings.reports_s3_bucket:
        raise RuntimeError("Report bucket is not configured")
    with session() as db:
        review = db.scalar(select(Review).where(Review.id == review_id).with_for_update())
        if review is None or review.status not in {"published", "dry_run"}:
            raise RuntimeError("Only completed reviews can be archived")
        if review.archive_uri:
            return review.archive_uri
        key = f"{settings.reports_s3_prefix.strip('/')}/{review.repo}/{review.number}/{review.head_sha}/{review.id}.json"
        report = {
            "schema_version": 1,
            "id": review.id,
            "repo": review.repo,
            "number": review.number,
            "head_sha": review.head_sha,
            "status": review.status,
            "findings": review.findings,
            "warnings": review.warnings,
            "github_review_id": review.github_review_id,
        }
        client = boto3.client(
            "s3",
            config=Config(
                connect_timeout=5,
                read_timeout=20,
                retries={"mode": "standard", "max_attempts": 2},
            ),
        )
        # Respect bucket default encryption (including customer-managed KMS).
        client.put_object(
            Bucket=settings.reports_s3_bucket,
            Key=key,
            Body=json.dumps(report, sort_keys=True).encode(),
            ContentType="application/json",
        )
        review.archive_uri = f"s3://{settings.reports_s3_bucket}/{key}"
        db.commit()
        return review.archive_uri
