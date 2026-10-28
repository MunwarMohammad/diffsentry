# AI GitHub PR Reviewer

A runnable implementation of the project in your `MATERIALS.zip` and [reference repository](https://github.com/data-guru0/GitHub-PR-Code-AI-Reviewer). Five FastAPI services validate GitHub webhooks, queue durable jobs, run four LangGraph review agents, publish commit-specific review comments, and collect recurring observations after merge.

**Start here:** the local demo works without GitHub, OpenAI, or AWS credentials. It uses explicitly labeled deterministic sample checks. Live mode uses OpenAI structured outputs and GitHub App installation tokens.

## Run on your Mac

Prerequisites: Docker Desktop running; [uv](https://docs.astral.sh/uv/) for Python commands. Run commands in this project folder.

```bash
cp .env.example .env
uv sync --frozen --python 3.12
uv run python -m scripts.demo
```

The offline demo writes `reports/demo.md` and `reports/demo.json` and prints three findings against the bundled calculator fixture. It makes no network calls.

Start the full system:

```bash
docker compose up -d --build --wait
uv run python -m scripts.smoke
```

The smoke test sends a signed webhook, verifies deduplication, waits for a dry-run review, simulates a merge, and verifies both background jobs completed. It uses the repository `demo/example`, which must remain in the local allowlist.

| Local endpoint | Purpose |
|---|---|
| http://localhost:8100/docs | Gateway interactive API documentation |
| http://localhost:8100/health | Gateway health |
| http://localhost:8101/docs | Review history, jobs, and retry API |
| http://localhost:8101/reviews | Stored reviews; bearer token required |
| http://localhost:8101/jobs | Job state, retry count, sanitized failure type |

In the intake API docs, use **Try it out** and set the `authorization` header to `Bearer local-demo-internal-token` for the default local setup. Ports can be changed with `GATEWAY_PORT` and `INTAKE_PORT` environment variables.

```bash
curl -H 'Authorization: Bearer local-demo-internal-token' http://localhost:8101/reviews
docker compose logs -f worker orchestrator
docker compose stop
```

`docker compose down` removes containers while retaining database and Redis volumes. Add `-v` only when you intend to erase local data.

## What is included

- HMAC-SHA256 webhook verification, input limits, repository allowlist, internal bearer authentication.
- PostgreSQL schema and Alembic migration; unique review identity `(repository, PR number, head SHA)`.
- Transactional database outbox, Redis/Celery workers, periodic dispatch, bounded retries, failed-job recovery.
- Four parallel LangGraph agents: correctness, security, style, architecture. Responses use Pydantic structured outputs.
- Added-line validation, deterministic deduplication, size limits, explicit incomplete-coverage warnings.
- GitHub App JWT/installation-token authentication; paginated changed files; stale-head checks; commit-bound `COMMENT` reviews.
- Reconciliation markers for retries after GitHub accepted a review but the database commit failed.
- Idempotent learning on merge. Observations are labeled unverified; merge is **not** treated as proof that a suggestion was accepted.
- Docker Compose, non-root image, Kubernetes manifests, optional AWS Terraform infrastructure.
- Prometheus metrics, provisioned Grafana dashboard, optional Langfuse generation spans.
- Tests, fixture evaluation, GitHub Actions CI, manual image release workflow, weekly offline regression evaluation.

## Architecture

```mermaid
flowchart LR
  GitHub -->|signed webhook| Gateway
  Gateway --> Intake[Webhook intake]
  Intake --> DB[(PostgreSQL + outbox)]
  Beat[Celery beat] --> Dispatcher
  Dispatcher --> DB
  Dispatcher --> Redis[(Redis)]
  Redis --> Worker
  Worker --> Orchestrator
  Orchestrator --> Agents[Four LangGraph reviewers]
  Agents --> OpenAI
  Orchestrator --> DB
  Orchestrator --> Publisher
  Publisher -->|commit-bound review| GitHub
  Worker --> Learner
  Learner --> DB
```

The publisher is the “reviewer service” in the supplied architecture; its name distinguishes posting from analysis. All services share one image and versioned domain package to avoid schema and authentication drift.

## Enable real reviews

Follow [the live setup guide](docs/LIVE_SETUP.md). You need your own GitHub App, a repository installation, an OpenAI API key, and a reachable HTTPS webhook URL. Set `REVIEW_MODE=live` and keep `PUBLISH_REVIEWS=false` for the first real analysis. Inspect the stored result before enabling posting.

The bundled model is configurable via `OPENAI_MODEL` and preserves the reference project's `gpt-4o-mini` default. Model availability depends on your OpenAI account. Four model calls are made per analyzed PR commit, with bounded input/output sizes and retries.

**Never paste API keys into chat or commit `.env`/PEM files.** Fill in your local `.env`. The Docker build context explicitly excludes it and the supplied reference materials.

## Tests and evaluation

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest --cov=reviewer --cov=services --cov-report=term-missing
uv run python -m scripts.evaluate
```

The default evaluation measures finding-location/category precision and recall on three labeled fixtures. It tests the deterministic demo, not AI quality. `uv run python -m scripts.evaluate --live` evaluates the configured model and incurs API usage; the tiny dataset is still not a production benchmark.

## Monitoring

```bash
docker compose --profile monitoring up -d
```

- Grafana: http://localhost:3100 — local credentials `admin` / `local-demo-only`.
- Prometheus: http://localhost:9190.
- Dashboard: **PR Reviewer · Service health**.
- Langfuse: optional, off by default. Set its public/secret keys, `LANGFUSE_BASE_URL`, and `LANGFUSE_ENABLED=true`. The code records agent generation spans without deliberately attaching source code or findings. Live tracing requires separate verification with your Langfuse project.

## Deployment and project guide

- [Live GitHub/OpenAI setup](docs/LIVE_SETUP.md)
- [AWS and Kubernetes deployment](docs/DEPLOYMENT.md)
- [Architecture, reliability tradeoffs, and source-material audit](docs/ARCHITECTURE.md)
- [Suggested build/learning order](docs/LEARNING_PATH.md)
- [Verification results](docs/VERIFICATION.md)

The repository contains deployment configuration; no cloud resources or remote GitHub changes are created by the local demo. AWS provisioning, live API behavior, and external tracing must be validated in your accounts before calling this production-ready.
