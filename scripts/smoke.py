"""Exercise signed webhook → durable job → four agents → dry run → learning."""

import hashlib
import hmac
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx

from reviewer.config import get_settings


def main():
    settings = get_settings()
    if settings.review_mode != "demo" or settings.publish_reviews:
        raise SystemExit("Smoke test requires REVIEW_MODE=demo and PUBLISH_REVIEWS=false")
    number = int(time.time())
    event = {
        "action": "opened",
        "repository": {"full_name": "demo/example"},
        "installation": {"id": 1},
        "pull_request": {
            "number": number,
            "head": {"sha": hashlib.sha1(uuid.uuid4().bytes).hexdigest()},
            "merged": False,
        },
    }
    authorization = {"Authorization": f"Bearer {settings.internal_api_token}"}
    with httpx.Client(timeout=10) as client:
        for _ in range(60):
            try:
                for port in (os.getenv("GATEWAY_PORT", "8100"), os.getenv("INTAKE_PORT", "8101")):
                    client.get(f"http://localhost:{port}/ready").raise_for_status()
                break
            except httpx.HTTPError:
                time.sleep(1)
        else:
            raise RuntimeError("Services did not become ready within 60 seconds")

        def send():
            data = json.dumps(event).encode()
            signature = (
                "sha256="
                + hmac.new(
                    settings.github_webhook_secret.encode(), data, hashlib.sha256
                ).hexdigest()
            )
            response = client.post(
                f"http://localhost:{os.getenv('GATEWAY_PORT', '8100')}/webhook/github",
                content=data,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": signature,
                },
            )
            response.raise_for_status()
            return response.json()

        result = send()
        review_id = result["review_id"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            duplicates = list(pool.map(lambda _: send(), range(8)))
        assert all(
            item["status"] == "duplicate" and item["review_id"] == review_id for item in duplicates
        )
        for _ in range(60):
            response = client.get(
                f"http://localhost:{os.getenv('INTAKE_PORT', '8101')}/reviews",
                headers=authorization,
            )
            response.raise_for_status()
            review = next(r for r in response.json() if r["id"] == review_id)
            if review["status"] == "dry_run":
                assert len(review["findings"]) == 3
                break
            time.sleep(2)
        else:
            raise RuntimeError("Review did not complete in 120 seconds")
        event["action"] = "closed"
        event["pull_request"]["merged"] = True
        send()
        for _ in range(30):
            response = client.get(
                f"http://localhost:{os.getenv('INTAKE_PORT', '8101')}/jobs", headers=authorization
            )
            response.raise_for_status()
            jobs = [j for j in response.json() if j["review_id"] == review_id]
            if len(jobs) == 2 and all(j["status"] == "done" for j in jobs):
                print(
                    json.dumps(
                        {
                            "result": "PASS",
                            "review_id": review_id,
                            "findings": len(review["findings"]),
                            "jobs": jobs,
                        },
                        indent=2,
                    )
                )
                return
            time.sleep(2)
        raise RuntimeError("Learning did not complete in 60 seconds")


if __name__ == "__main__":
    main()
