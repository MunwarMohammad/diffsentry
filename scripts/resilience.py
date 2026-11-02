"""Local Compose failure drill: duplicate burst and temporary broker outage."""

import hashlib
import hmac
import json
import os
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from reviewer.config import get_settings


def main():
    settings = get_settings()
    if settings.review_mode != "demo" or settings.publish_reviews:
        raise SystemExit("This drill requires demo mode with publication disabled")
    gateway = f"http://localhost:{os.getenv('GATEWAY_PORT', '8100')}"
    intake = f"http://localhost:{os.getenv('INTAKE_PORT', '8101')}"
    auth = {"Authorization": f"Bearer {settings.internal_api_token}"}
    event = {
        "action": "opened",
        "repository": {"full_name": "demo/example"},
        "installation": {"id": 1},
        "pull_request": {
            "number": int(time.time()),
            "head": {"sha": hashlib.sha1(uuid.uuid4().bytes).hexdigest()},
        },
    }
    body = json.dumps(event).encode()
    signature = (
        "sha256="
        + hmac.new(settings.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    )
    with httpx.Client(timeout=30) as client:

        def send(_):
            response = client.post(
                f"{gateway}/webhook/github",
                content=body,
                headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": signature},
            )
            response.raise_for_status()
            return response.json()

        try:
            subprocess.run(["docker", "compose", "stop", "redis"], check=True, capture_output=True)
            with ThreadPoolExecutor(max_workers=16) as pool:
                results = list(pool.map(send, range(100)))
            ids = {r["review_id"] for r in results}
            assert len(ids) == 1, "Concurrent duplicate events created multiple reviews"
            review_id = ids.pop()
            response = client.get(f"{intake}/jobs", headers=auth)
            response.raise_for_status()
            jobs = [j for j in response.json() if j["review_id"] == review_id]
            assert len(jobs) == 1, "Expected one durable job while broker is down"
        finally:
            subprocess.run(
                ["docker", "compose", "up", "-d", "redis"], check=True, capture_output=True
            )
        for _ in range(90):
            response = client.get(f"{intake}/reviews", headers=auth)
            response.raise_for_status()
            review = next(r for r in response.json() if r["id"] == review_id)
            if review["status"] == "dry_run":
                break
            time.sleep(2)
        else:
            raise RuntimeError("Accepted job did not recover after Redis restarted")
    report = {
        "result": "PASS",
        "simultaneous_deliveries": 100,
        "unique_reviews": 1,
        "durable_jobs": 1,
        "broker_outage_recovered": True,
        "review_id": review_id,
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/resilience.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
