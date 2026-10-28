import hashlib
import hmac
import json

import httpx
from fastapi import HTTPException, Request

from reviewer.api import headers, make_app
from reviewer.config import get_settings

app = make_app("gateway", database=False)


@app.post("/webhook/github", status_code=202)
async def github_webhook(request: Request):
    settings = get_settings()
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > settings.max_webhook_bytes:
            raise HTTPException(413, "Webhook exceeds size limit")
    expected = (
        "sha256="
        + hmac.new(settings.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    )
    signature = request.headers.get("x-hub-signature-256", "")
    if not hmac.compare_digest(expected.encode(), signature.encode()):
        raise HTTPException(401, "Invalid webhook signature")
    event = request.headers.get("x-github-event", "")
    if event == "ping":
        return {"status": "pong"}
    if event != "pull_request":
        return {"status": "ignored"}
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError()
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Expected a JSON object") from None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{settings.webhook_url}/events",
                content=bytes(body),
                headers={
                    **headers(),
                    "Content-Type": "application/json",
                    "X-GitHub-Event": event,
                },
            )
        if response.status_code in (403, 422):
            raise HTTPException(response.status_code, "Event rejected by intake")
        response.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(503, "Intake unavailable; redeliver this webhook") from None
    return response.json()
