# Connect GitHub and OpenAI

## 1. Create a GitHub App

In GitHub developer settings, create a GitHub App that belongs to your account/organization. Give it these repository permissions:

| Permission | Access |
|---|---|
| Metadata | Read |
| Contents | Read |
| Pull requests | Read and write |

Subscribe to **Pull request** events. Install the App only on the repositories you want reviewed. Generate a private key and record the App ID (not the OAuth Client ID). Use your own App and credentials; the materials are reference documents, not account configuration.

Set the webhook URL to `https://YOUR_DOMAIN/webhook/github`. For local testing, use a trusted HTTPS tunnel pointing to `localhost:8100`. Configure the same webhook secret in the GitHub App and `.env`. Keep SSL verification enabled.

See [GitHub App creation](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app), [installation authentication](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation), and [webhook validation](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries).

## 2. Configure the local environment

Copy `.env.example` to `.env` if it does not already exist. Edit it locally:

```dotenv
ENVIRONMENT=production
REVIEW_MODE=live
PUBLISH_REVIEWS=false
ALLOWED_REPOSITORIES=your-owner/your-repository
GITHUB_APP_ID=your-app-id
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nYOUR_PEM_BODY\n-----END RSA PRIVATE KEY-----"
OPENAI_API_KEY=your-openai-project-key
OPENAI_MODEL=gpt-4o-mini
GITHUB_WEBHOOK_SECRET=your-random-secret-at-least-32-characters
INTERNAL_API_TOKEN=a-different-random-secret-at-least-32-characters
```

Generate each secret independently with `openssl rand -hex 32`. Do not reuse the local defaults. For multiple repositories, use a comma-separated allowlist. Compose supplies PostgreSQL, Redis and service URLs automatically; its database credentials are local-development credentials only. Do not expose PostgreSQL/Redis or deploy the development Compose configuration publicly.

Alternatively, set `GITHUB_APP_PRIVATE_KEY_PATH` and mount the PEM at that exact container path using a local Compose override. A path on your Mac is not automatically available inside a container.

The integration uses [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs) through `responses.parse`, verifies completion, and treats refusals or malformed output as failed analysis rather than a clean review. `store=false` is sent with API requests. Review source is still sent to OpenAI in live mode.

## 3. Review without posting

```bash
docker compose up -d --build --wait
```

Create a small PR in the installed repository. Review the GitHub App's delivery history: successful delivery should return 202. Inspect intake `/reviews` and `/jobs` using the configured internal bearer token. The final status should be `dry_run`, with real AI findings and any coverage limitations.

If the webhook gets 503, redeliver it from GitHub's delivery UI after fixing connectivity. The system retries accepted jobs itself; it cannot recover a webhook it never accepted.

## 4. Enable comments

Change `PUBLISH_REVIEWS=true`, recreate services with `docker compose up -d`, and push a **new commit** or open a new test PR. Completed dry runs are intentionally not republished when the configuration changes. Each head SHA is processed once.

Expected behavior:

1. A GitHub review is attached to the analyzed SHA, with inline comments only on validated added lines.
2. Even a clean review gets a summary, including any excluded files.
3. A newer commit or closed PR causes obsolete work to be marked `superseded`.
4. Repeated deliveries do not create duplicate database jobs.
5. A merged reviewed head triggers one learning job.

Publication uses the `COMMENT` event; it does not approve, reject, merge, or modify source code.

## Recovery

Check `/jobs` for failures. `last_error` contains a sanitized exception type; service logs have the context needed to diagnose provider errors. Repair configuration, then `POST /jobs/JOB_ID/retry` with the internal bearer header. This only resets terminally failed jobs. It does not repost completed reviews.

Check App installation permissions for GitHub 403 errors, OpenAI account/model availability for model errors, and service URLs/Redis availability for connectivity errors. The outbox ensures accepted jobs remain in PostgreSQL if Redis is unavailable.
