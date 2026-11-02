"""Read-only local configuration/readiness check; never prints secret values."""

import argparse
import json
import os

import httpx
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from reviewer.config import Settings


def inspect(settings, live=False):
    checks = []

    def add(name, ok, instruction):
        checks.append({"check": name, "ok": bool(ok), "next_step": "" if ok else instruction})

    add(
        "unique webhook secret",
        len(settings.github_webhook_secret) >= 32
        and not settings.github_webhook_secret.startswith("local-demo"),
        "Run scripts.init_env or set a random 32+ character secret in .env",
    )
    add(
        "unique internal token",
        len(settings.internal_api_token) >= 32
        and settings.internal_api_token != settings.github_webhook_secret,
        "Set a separate random 32+ character INTERNAL_API_TOKEN",
    )
    if live:
        add(
            "OpenAI credential",
            bool(settings.openai_api_key),
            "Set OPENAI_API_KEY in .env; do not paste it in chat",
        )
        add(
            "GitHub App ID",
            settings.github_app_id.isdigit(),
            "Register/install a GitHub App and set its numeric GITHUB_APP_ID",
        )
        valid_key = False
        try:
            from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

            key = load_pem_private_key(settings.private_key().encode(), password=None)
            valid_key = isinstance(key, RSAPrivateKey)
        except (ValueError, TypeError, OSError):
            pass
        add(
            "GitHub App RSA key",
            valid_key,
            "Set GITHUB_APP_PRIVATE_KEY or a readable GITHUB_APP_PRIVATE_KEY_PATH",
        )
        add(
            "repository allowlist",
            bool(settings.allowed_repositories.strip()),
            "Set ALLOWED_REPOSITORIES to the installed test repository",
        )
        add(
            "live analysis mode",
            settings.review_mode == "live",
            "Set REVIEW_MODE=live after configuring credentials",
        )
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--services", action="store_true")
    args = parser.parse_args()
    try:
        checks = inspect(Settings(), live=args.live)
    except ValueError:
        print("Configuration invalid. Check .env against .env.example; values are not displayed.")
        raise SystemExit(1) from None
    if args.services:
        for name, port in [
            ("gateway", os.getenv("GATEWAY_PORT", "8100")),
            ("intake", os.getenv("INTAKE_PORT", "8101")),
        ]:
            try:
                response = httpx.get(f"http://localhost:{port}/ready", timeout=5)
                ok = response.status_code == 200
            except httpx.HTTPError:
                ok = False
            checks.append(
                {
                    "check": f"{name} readiness",
                    "ok": ok,
                    "next_step": "" if ok else "Start Docker Compose and inspect service logs",
                }
            )
    print(
        json.dumps(
            {
                "checks": checks,
                "ready": all(c["ok"] for c in checks),
                "scope": "Local configuration only; provider authentication and real review quality still require live testing.",
            },
            indent=2,
        )
    )
    raise SystemExit(0 if all(c["ok"] for c in checks) else 1)


if __name__ == "__main__":
    main()
