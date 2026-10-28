import hashlib

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from reviewer.api import authorize, make_app
from reviewer.database import session
from reviewer.models import Pattern, Review, ReviewRequest

app = make_app("learner")


@app.post("/learn", dependencies=[Depends(authorize)])
def learn(request: ReviewRequest):
    with session() as db:
        review = db.scalar(select(Review).where(Review.id == request.review_id).with_for_update())
        if review is None:
            raise HTTPException(404, "Review not found")
        if review.learned or review.status == "superseded":
            return {"status": "skipped"}
        if review.status not in {"published", "dry_run"}:
            raise HTTPException(503, "Waiting for review completion")
        insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
        seen = set()
        for finding in review.findings:
            if finding["severity"] not in {"warning", "error"}:
                continue
            text = " ".join(finding["message"].split())
            key = hashlib.sha256(text.lower().encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            stmt = insert(Pattern).values(repo=review.repo, pattern_key=key, text=text, frequency=1)
            db.execute(
                stmt.on_conflict_do_update(
                    index_elements=["repo", "pattern_key"],
                    set_={"frequency": Pattern.frequency + 1},
                )
            )
        review.learned = True
        db.commit()
        return {"status": "learned", "patterns": len(seen)}
