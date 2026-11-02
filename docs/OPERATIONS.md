# DiffSentry operations

## Job recovery

Jobs move through `pending`, `queued`, `running`, and `done`. After six failed attempts they become `failed`. Query the protected intake `/jobs` endpoint with your `.env` internal bearer token. Fix the reported cause, then POST `/jobs/JOB_ID/retry` to reset that failed job. Completion and retry states are persisted in PostgreSQL.

Each dispatch has a unique token. Stale broker messages cannot steal new attempts or skip the backoff, and expired workers cannot overwrite a newer attempt's status. A queued delivery expires after a minute; running work has a ten-minute recovery lease.

## Monitoring

Start `docker compose --profile monitoring up -d`. Service metrics remain at `/metrics`; intake's `/queue-metrics` also publishes persisted job counts by status/kind and oldest overdue work. Prometheus loads `monitoring/alerts.yml`:

- Service unavailable for two minutes.
- Terminal failures for one minute.
- Work overdue by more than five minutes for two minutes.

These rules appear in Prometheus's Alerts page. Configure Alertmanager and a destination before expecting email, Slack or pager notifications; this project does not send notifications to an account by default.

Validate rules with:

```bash
docker compose exec -T prometheus promtool check rules /etc/prometheus/alerts.yml
```

## Local failure drill and backups

```bash
uv run python -m scripts.resilience
uv run python -m scripts.backup --verify
```

The first command temporarily stops only this Compose project's Redis, sends 100 concurrent signed duplicate events, restores Redis in a `finally` block, and checks recovery. Use demo mode, and avoid running other tests against the same stack simultaneously.

The backup command writes a PostgreSQL custom-format dump with owner-only permissions under ignored `reports/backups/`. `--verify` creates a temporary database, restores the dump, compares review/job/pattern counts, and removes that disposable database. Stop test traffic during the verification. Store real backups in a separately protected location with retention and off-machine copies; a file on the same computer does not protect against machine loss.

For a real recovery, restore the selected dump into a new PostgreSQL database, set `DATABASE_URL`, run Alembic and validate it, then switch services. Never overwrite a production database as a routine test.

## Optional S3 report archival

Set `REPORTS_S3_BUCKET` and optionally `REPORTS_S3_PREFIX`. Supply AWS credentials via the standard SDK provider chain. In Kubernetes use a properly scoped workload IAM role; the default manifests do not configure that identity. Grant `s3:PutObject` only for the chosen report prefix, with KMS permissions if your bucket encryption requires them.

Completed published/dry-run reviews atomically enqueue a separate archive job. Its stable object key includes repository, PR, SHA and review ID. It stores findings, warnings and publication ID, never App tokens or private keys. Archive retries do not repeat GitHub publication. The SDK respects the bucket's default encryption.

`archive_uri` on the protected review history records the stored location. Inspect and retry failed archive jobs just like analysis jobs. Storage contents can contain private code-review information; choose access and retention accordingly.

S3 calls are covered by mocked integration tests; a real upload remains a separate account-specific verification step.
