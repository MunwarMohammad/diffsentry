from fastapi import Depends, HTTPException
from sqlalchemy import select

from reviewer.api import authorize, make_app
from reviewer.config import get_settings
from reviewer.database import session
from reviewer.github import StaleReview, github_client, publish
from reviewer.models import Review, ReviewRequest
from reviewer.summary import summary

app = make_app("publisher")


@app.post("/post-review", dependencies=[Depends(authorize)])
def post_review(request: ReviewRequest):
    with session() as db:
        review = db.scalar(select(Review).where(Review.id == request.review_id).with_for_update())
        if review is None:
            raise HTTPException(404, "Review not found")
        if review.status in {"published", "dry_run", "superseded"}:
            return {"status": review.status}
        if review.status != "analyzed":
            raise HTTPException(409, "Analysis is not complete")
        body = summary(review)
        if not get_settings().publish_reviews:
            review.status = "dry_run"
        else:
            comments = [
                {
                    "path": f["file"],
                    "line": f["line"],
                    "side": "RIGHT",
                    "body": f"**{f['severity'].upper()}** ({f['agent']})\n\n{f['message']}",
                }
                for f in review.findings
            ]
            try:
                with github_client(review.installation_id) as client:
                    review.github_review_id = publish(client, review, body, comments)
                review.status = "published"
            except StaleReview:
                review.status = "superseded"
        db.commit()
        return {"status": review.status, "summary": body}
