import hashlib
import hmac
import json

import httpx
import respx
from fastapi.testclient import TestClient

from reviewer.config import get_settings
from services.gateway.main import app


def signed(body, event="pull_request"):
    return {
        "X-Hub-Signature-256": "sha256="
        + hmac.new(b"test-webhook-secret", body, hashlib.sha256).hexdigest(),
        "X-GitHub-Event": event,
    }


def test_unsigned_rejected(event):
    with TestClient(app) as client:
        assert client.post("/webhook/github", json=event).status_code == 401


@respx.mock
def test_signed_forwarding(event):
    body = json.dumps(event).encode()
    route = respx.post("http://localhost:8001/events").mock(
        return_value=httpx.Response(202, json={"status": "accepted"})
    )
    with TestClient(app) as client:
        assert (
            client.post("/webhook/github", content=body, headers=signed(body)).json()["status"]
            == "accepted"
        )
    assert route.calls[0].request.content == body
    assert route.calls[0].request.headers["authorization"] == "Bearer test-internal-token"


@respx.mock
def test_intake_failure_is_retryable(event):
    respx.post("http://localhost:8001/events").mock(return_value=httpx.Response(500))
    body = json.dumps(event).encode()
    with TestClient(app) as client:
        assert client.post("/webhook/github", content=body, headers=signed(body)).status_code == 503


def test_ping_and_invalid_json():
    with TestClient(app) as client:
        assert (
            client.post("/webhook/github", content=b"{}", headers=signed(b"{}", "ping")).json()[
                "status"
            ]
            == "pong"
        )
        assert (
            client.post("/webhook/github", content=b"oops", headers=signed(b"oops")).status_code
            == 400
        )
        assert (
            client.post("/webhook/github", content=b"[]", headers=signed(b"[]")).status_code == 400
        )


def test_size_limit():
    get_settings().max_webhook_bytes = 2
    with TestClient(app) as client:
        assert client.post("/webhook/github", content=b"large").status_code == 413
