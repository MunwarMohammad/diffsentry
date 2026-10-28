import time
from contextlib import contextmanager

import httpx
import jwt

from reviewer.config import get_settings


class StaleReview(Exception):
    pass


@contextmanager
def github_client(installation_id):
    settings = get_settings()
    if not settings.github_app_id or not settings.private_key():
        raise RuntimeError("GitHub App ID and private key are required")
    now = int(time.time())
    token = jwt.encode(
        {"iat": now - 60, "exp": now + 540, "iss": settings.github_app_id},
        settings.private_key(),
        algorithm="RS256",
    )
    with httpx.Client(
        base_url="https://api.github.com",
        timeout=30,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {token}",
        },
    ) as client:
        identity = client.get("/app")
        identity.raise_for_status()
        client.reviewer_bot_login = f"{identity.json()['slug']}[bot]"
        response = client.post(f"/app/installations/{installation_id}/access_tokens")
        response.raise_for_status()
        client.headers["Authorization"] = f"Bearer {response.json()['token']}"
        yield client


def check_head(client, review):
    response = client.get(f"/repos/{review.repo}/pulls/{review.number}")
    response.raise_for_status()
    data = response.json()
    if data["head"]["sha"] != review.head_sha or data["state"] != "open":
        raise StaleReview("Pull request head changed or PR is closed")
    return data


def fetch_files(client, review):
    info = check_head(client, review)
    files = []
    for page in range(1, 31):
        response = client.get(
            f"/repos/{review.repo}/pulls/{review.number}/files",
            params={"per_page": 100, "page": page},
        )
        response.raise_for_status()
        batch = response.json()
        files.extend(batch)
        if len(batch) < 100:
            break
    if len(files) != info["changed_files"]:
        raise RuntimeError("GitHub returned an incomplete file list")
    check_head(client, review)
    return files


def existing_review(client, review, marker):
    for page in range(1, 101):
        response = client.get(
            f"/repos/{review.repo}/pulls/{review.number}/reviews",
            params={"per_page": 100, "page": page},
        )
        response.raise_for_status()
        batch = response.json()
        for item in batch:
            app_id = (item.get("performed_via_github_app") or {}).get("id")
            if (
                marker in (item.get("body") or "")
                and item.get("commit_id") == review.head_sha
                and (
                    str(app_id) == get_settings().github_app_id
                    or (
                        (item.get("user") or {}).get("type") == "Bot"
                        and (item.get("user") or {}).get("login")
                        == getattr(client, "reviewer_bot_login", None)
                        and getattr(client, "reviewer_bot_login", None) is not None
                    )
                )
            ):
                return str(item["id"])
        if len(batch) < 100:
            return None
    raise RuntimeError("Review history exceeds reconciliation limit")


def publish(client, review, body, comments):
    marker = f"<!-- pr-reviewer:{review.id}:{review.head_sha} -->"
    previous = existing_review(client, review, marker)
    if previous:
        return previous
    check_head(client, review)
    payload = {
        "commit_id": review.head_sha,
        "event": "COMMENT",
        "body": f"{body}\n\n{marker}",
        "comments": comments,
    }
    response = client.post(f"/repos/{review.repo}/pulls/{review.number}/reviews", json=payload)
    # Any error is visible and retried through the durable job; never silently discard inline comments.
    response.raise_for_status()
    return str(response.json()["id"])
