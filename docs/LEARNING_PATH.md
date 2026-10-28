# Build and learn the project in order

Each stage has runnable code so you can understand the full project without provisioning AWS first.

1. **Understand the workflow.** Read the README diagram and `reviewer/models.py`. Follow how a PR head becomes a review and a job.
2. **Run an offline review.** Run `uv run python -m scripts.demo`. Read `reviewer/diff.py` and `reviewer/graph.py`; compare the fixture to the generated report.
3. **Verify webhook security.** Read `services/gateway/main.py` and `tests/test_gateway.py`. Understand why HMAC uses the original body bytes.
4. **Follow durable work.** Read webhook intake and `reviewer/worker.py`. Stop Redis temporarily in your own test stack to understand why jobs remain in PostgreSQL; restart it to resume dispatch.
5. **Run the complete stack.** Use Docker Compose and the smoke script. Inspect `/reviews`, `/jobs`, and worker logs.
6. **Connect real APIs.** Follow `LIVE_SETUP.md` with dry-run publication. Inspect real model findings before enabling comments.
7. **Understand retries and stale work.** Read GitHub integration tests. Push a second commit while a review is running and inspect the status of both heads.
8. **Observe and evaluate.** Enable Grafana/Prometheus. Run the labeled fixture evaluation, then expand it with examples from your own codebase.
9. **Deploy deliberately.** Read `DEPLOYMENT.md`, review Terraform output, and configure your own cloud accounts. Local success is the prerequisite, not a substitute for cloud validation.

For an interview or portfolio explanation, focus on the choices you can demonstrate: signature verification, transactional outbox, parallel review graph, structured output, location validation, SHA-specific publication, and idempotent merge learning.
