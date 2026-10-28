from types import SimpleNamespace

import httpx
import pytest
import respx

from reviewer.config import get_settings
from reviewer.github import StaleReview, fetch_files, publish


@pytest.fixture
def review():
    return SimpleNamespace(id="review-id", repo="demo/example", number=1, head_sha="a" * 40)


@respx.mock
def test_stale_commit_never_posts(review):
    respx.get("https://api.github.com/repos/demo/example/pulls/1/reviews").respond(200, json=[])
    respx.get("https://api.github.com/repos/demo/example/pulls/1").respond(
        200, json={"head": {"sha": "b" * 40}, "state": "open"}
    )
    with httpx.Client(base_url="https://api.github.com") as client, pytest.raises(StaleReview):
        publish(client, review, "summary", [])
    assert all(call.request.method == "GET" for call in respx.calls)


@respx.mock
def test_publish_tied_to_commit_and_comment_event(review):
    respx.get("https://api.github.com/repos/demo/example/pulls/1/reviews").respond(200, json=[])
    respx.get("https://api.github.com/repos/demo/example/pulls/1").respond(
        200, json={"head": {"sha": review.head_sha}, "state": "open"}
    )
    route = respx.post("https://api.github.com/repos/demo/example/pulls/1/reviews").respond(
        200, json={"id": 5}
    )
    with httpx.Client(base_url="https://api.github.com") as client:
        assert publish(client, review, "summary", []) == "5"
    import json

    payload = json.loads(route.calls[0].request.content)
    assert payload["commit_id"] == review.head_sha
    assert payload["event"] == "COMMENT"


@respx.mock
def test_reconcile_after_post_success_and_db_failure(review):
    get_settings().github_app_id = "42"
    marker = f"<!-- pr-reviewer:{review.id}:{review.head_sha} -->"
    respx.get("https://api.github.com/repos/demo/example/pulls/1/reviews").respond(
        200,
        json=[
            {
                "id": 7,
                "body": marker,
                "commit_id": review.head_sha,
                "performed_via_github_app": {"id": 42},
            }
        ],
    )
    with httpx.Client(base_url="https://api.github.com") as client:
        assert publish(client, review, "summary", []) == "7"
    assert len(respx.calls) == 1


@respx.mock
def test_files_pagination_and_changed_head(review):
    route = respx.get("https://api.github.com/repos/demo/example/pulls/1")
    route.side_effect = [
        httpx.Response(
            200, json={"head": {"sha": review.head_sha}, "state": "open", "changed_files": 1}
        ),
        httpx.Response(200, json={"head": {"sha": "b" * 40}, "state": "open"}),
    ]
    respx.get("https://api.github.com/repos/demo/example/pulls/1/files").respond(
        200, json=[{"filename": "a.py"}]
    )
    with httpx.Client(base_url="https://api.github.com") as client, pytest.raises(StaleReview):
        fetch_files(client, review)


@respx.mock
def test_app_authentication_and_bot_identity():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from reviewer.github import github_client

    settings = get_settings()
    settings.github_app_id = "42"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings.github_app_private_key = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    respx.get("https://api.github.com/app").respond(200, json={"slug": "my-reviewer"})
    route = respx.post("https://api.github.com/app/installations/1/access_tokens").respond(
        201, json={"token": "installation-test-token"}
    )
    with github_client(1) as client:
        assert client.reviewer_bot_login == "my-reviewer[bot]"
        assert client.headers["authorization"] == "Bearer installation-test-token"
    import jwt

    payload = jwt.decode(
        route.calls[0].request.headers["authorization"].split()[1],
        key.public_key(),
        algorithms=["RS256"],
    )
    assert payload["iss"] == "42"
    assert 0 < payload["exp"] - payload["iat"] <= 600


@respx.mock
def test_reconcile_bot_identity_without_app_metadata(review):
    marker = f"<!-- pr-reviewer:{review.id}:{review.head_sha} -->"
    respx.get("https://api.github.com/repos/demo/example/pulls/1/reviews").respond(
        200,
        json=[
            {
                "id": 9,
                "body": marker,
                "commit_id": review.head_sha,
                "user": {"type": "Bot", "login": "my-reviewer[bot]"},
            }
        ],
    )
    with httpx.Client(base_url="https://api.github.com") as client:
        client.reviewer_bot_login = "my-reviewer[bot]"
        assert publish(client, review, "summary", []) == "9"


@respx.mock
def test_copied_marker_from_human_cannot_suppress_review(review):
    marker = f"<!-- pr-reviewer:{review.id}:{review.head_sha} -->"
    respx.get("https://api.github.com/repos/demo/example/pulls/1/reviews").respond(
        200,
        json=[
            {
                "id": 9,
                "body": marker,
                "commit_id": review.head_sha,
                "user": {"type": "User", "login": "someone"},
            }
        ],
    )
    respx.get("https://api.github.com/repos/demo/example/pulls/1").respond(
        200, json={"head": {"sha": review.head_sha}, "state": "open"}
    )
    route = respx.post("https://api.github.com/repos/demo/example/pulls/1/reviews").respond(
        200, json={"id": 10}
    )
    with httpx.Client(base_url="https://api.github.com") as client:
        assert publish(client, review, "summary", []) == "10"
    assert route.called
