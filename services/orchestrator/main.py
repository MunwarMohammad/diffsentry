import asyncio
import json
from pathlib import Path

import httpx
from fastapi import Depends, HTTPException
from sqlalchemy import select

from reviewer.api import authorize, headers, make_app
from reviewer.config import get_settings
from reviewer.database import session
from reviewer.diff import prepare_files
from reviewer.github import StaleReview, fetch_files, github_client
from reviewer.graph import review_files
from reviewer.models import Pattern, Review, ReviewRequest

app = make_app("orchestrator")


@app.post("/analyze", dependencies=[Depends(authorize)])
def analyze(request: ReviewRequest):
    settings = get_settings()
    # PostgreSQL row locks serialize duplicate deliveries. SQLite is only for single-process demos.
    with session() as db:
        review = db.scalar(select(Review).where(Review.id == request.review_id).with_for_update())
        if review is None:
            raise HTTPException(404, "Review not found")
        if review.status in {"published", "dry_run", "superseded"}:
            return {"status": review.status}
        if review.status != "analyzed":
            if settings.review_mode == "demo":
                files = json.loads(Path("fixtures/files.json").read_text())
            else:
                try:
                    with github_client(review.installation_id) as client:
                        files = fetch_files(client, review)
                except StaleReview:
                    review.status = "superseded"
                    db.commit()
                    return {"status": "superseded"}
            files, warnings = prepare_files(files, settings.max_diff_chars)
            patterns = db.scalars(
                select(Pattern.text)
                .where(Pattern.repo == review.repo)
                .order_by(Pattern.frequency.desc())
                .limit(10)
            ).all()
            result = (
                asyncio.run(asyncio.wait_for(review_files(files, patterns), timeout=300))
                if files
                else {"findings": [], "warnings": ["No eligible added lines available for review"]}
            )
            review.findings = [f.model_dump() for f in result["findings"]]
            review.warnings = warnings + result["warnings"]
            if settings.review_mode == "demo":
                review.warnings += [
                    "DEMO: deterministic sample rules, not an AI review of this repository"
                ]
            review.status = "analyzed"
            db.commit()
    # Release the DB lock before the publisher takes its own lock.
    with httpx.Client(timeout=180) as client:
        response = client.post(
            f"{settings.publisher_url}/post-review", json=request.model_dump(), headers=headers()
        )
        response.raise_for_status()
    return response.json()
