# Verification record

Verified locally on October 27, 2026 (America/Chicago), using Python 3.12 and Docker Desktop on this Mac.

| Check | Result |
|---|---|
| Ruff lint and formatting | Passed |
| Unit/service tests | 30 passed |
| Statement coverage, application/services | 89% |
| Offline four-agent demo | Three findings with correct fixture line locations |
| Labeled fixture evaluation | Precision 1.0, recall 1.0 in deterministic demo mode |
| Alembic migration + schema comparison | Upgrade succeeded; no new upgrade operations detected |
| Docker image + Compose startup | Passed; five HTTP services ready |
| End-to-end signed webhook | Passed through PostgreSQL, Redis, Celery, orchestrator and publisher dry run |
| Duplicate delivery | Same review ID; no extra review job |
| Merge learning | Completed once; both jobs reached done |
| Prometheus | All five service targets up |
| Grafana | Health OK; provisioned dashboard accessible |
| Terraform | Init without backend and validate passed; provider lock file generated |
| Kubernetes | YAML parsed and Kustomize rendered successfully |

Tests cover signature rejection and forwarding, input limits, service authentication, repository allowlisting, durable intake, per-head identity, structured model-output handling, agent failure propagation, changed-line validation, retries, abandoned-worker recovery, duplicate suppression, GitHub JWT generation, bot-identity reconciliation, stale heads, clean review completion and idempotent learning.

The test run emits one upstream Starlette/AnyIO deprecation warning; it does not affect these results.

## Not verified against external accounts

- Real OpenAI output quality, available model access, account quota and billing.
- Actual GitHub App installation, internet webhook delivery, and comment posting.
- Langfuse project ingestion.
- AWS provisioning, Kubernetes rollout, ingress/DNS/ACM certificates and cloud recovery.
- Production scale, load, multi-AZ operation, disaster recovery, or security certification.

The demo deliberately never posts to GitHub. Unit tests mock external APIs. Fixture scores are regression results on a tiny deterministic dataset, not evidence of model accuracy. Terraform validation verifies configuration/schema compatibility, not availability or successful provisioning in your AWS account.
