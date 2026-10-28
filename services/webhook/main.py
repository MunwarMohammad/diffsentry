from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from reviewer.api import authorize, make_app
from reviewer.config import get_settings
from reviewer.database import session
from reviewer.models import Job, Review

app = make_app("webhook")


class Head(BaseModel):
    sha: str = Field(pattern=r"^[a-fA-F0-9]{40,64}$")


class PullRequest(BaseModel):
    number: int = Field(gt=0)
    head: Head
    merged: bool = False
    draft: bool = False


class Repository(BaseModel):
    full_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class Installation(BaseModel):
    id: int = Field(gt=0)


class Event(BaseModel):
    action: str
    pull_request: PullRequest
    repository: Repository
    installation: Installation


@app.post("/events", dependencies=[Depends(authorize)], status_code=202)
def receive_event(event: Event):
    repo = event.repository.full_name.lower()
    if not get_settings().permits(repo):
        raise HTTPException(403, "Repository is not allowed")
    pr = event.pull_request
    kind = "learn" if event.action == "closed" and pr.merged else "analyze"
    if kind == "analyze" and (
        event.action not in {"opened", "reopened", "synchronize", "ready_for_review"} or pr.draft
    ):
        return {"status": "ignored"}
    with session() as db:
        try:
            review = db.scalar(
                select(Review).where(
                    Review.repo == repo,
                    Review.number == pr.number,
                    Review.head_sha == pr.head.sha.lower(),
                )
            )
            if kind == "learn" and review is None:
                return {"status": "ignored", "reason": "No review for the merged head"}
            if review is None:
                review = Review(
                    repo=repo,
                    number=pr.number,
                    head_sha=pr.head.sha.lower(),
                    installation_id=event.installation.id,
                )
                db.add(review)
                db.flush()
            elif review.installation_id != event.installation.id:
                raise HTTPException(409, "Installation changed for this review")
            job = db.scalar(select(Job).where(Job.review_id == review.id, Job.kind == kind))
            if job:
                return {"status": "duplicate", "review_id": review.id, "job_status": job.status}
            db.add(Job(review_id=review.id, kind=kind))
            db.commit()
            return {"status": "accepted", "review_id": review.id}
        except IntegrityError:
            db.rollback()
            review = db.scalar(
                select(Review).where(
                    Review.repo == repo,
                    Review.number == pr.number,
                    Review.head_sha == pr.head.sha.lower(),
                )
            )
            if review is None:
                raise
            return {"status": "duplicate", "review_id": review.id}


@app.get("/reviews", dependencies=[Depends(authorize)])
def reviews():
    with session() as db:
        items = db.scalars(select(Review).order_by(Review.created_at.desc()).limit(100))
        return [
            {
                "id": r.id,
                "repo": r.repo,
                "number": r.number,
                "head_sha": r.head_sha,
                "status": r.status,
                "findings": r.findings,
                "warnings": r.warnings,
            }
            for r in items
        ]


@app.get("/jobs", dependencies=[Depends(authorize)])
def jobs():
    with session() as db:
        items = db.scalars(select(Job).order_by(Job.available_at.desc()).limit(100))
        return [
            {
                "id": j.id,
                "review_id": j.review_id,
                "kind": j.kind,
                "status": j.status,
                "attempts": j.attempts,
                "last_error": j.last_error,
            }
            for j in items
        ]


@app.post("/jobs/{job_id}/retry", dependencies=[Depends(authorize)])
def retry_job(job_id: str):
    from reviewer.models import now

    with session() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job is None:
            raise HTTPException(404, "Job not found")
        if job.status != "failed":
            raise HTTPException(409, "Only failed jobs can be retried manually")
        job.status, job.attempts, job.last_error, job.available_at = "pending", 0, None, now()
        db.commit()
        return {"status": "pending"}
