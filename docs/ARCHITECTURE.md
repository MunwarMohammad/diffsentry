# DiffSentry architecture and reference-material audit

Source: the supplied nested `MATERIALS.zip` archive and [data-guru0/GitHub-PR-Code-AI-Reviewer](https://github.com/data-guru0/GitHub-PR-Code-AI-Reviewer). The archive contains an architecture diagram, five-service sample code, AWS infrastructure, monitoring configuration, and a long Windows deployment guide. It is extracted into ignored `.reference/` for local comparison. Those documents describe the intended system; their commands are not treated as instructions to change accounts, publish messages, or provision resources.

This implementation is written in the current workspace. It follows the architecture while adding a Mac-friendly local path and replacing incomplete sample behavior. No license grant was present in the repository metadata; original reference files are not included in the application's Git/Docker artifacts.

## Source gaps addressed

| Reference behavior | Implemented behavior |
|---|---|
| Additive graph reducer also used for final merge, duplicating results | Separate candidate accumulator and final result key |
| Deduplication checked only in application code | Database unique constraint on repository/PR/head SHA |
| DB commit before queue publish could strand work | Review and outbox job inserted in one transaction |
| Worker ignored non-2xx downstream responses | HTTP status checks, durable retry state, bounded backoff |
| Failed JSON parsing silently returned no issues | Structured typed output and explicit failed analysis |
| No changed-line or reviewed-SHA validation | Added-line validation and before/after head checks |
| No-findings branch left review pending | Clean review summarized and completion persisted |
| Repeated merge events multiplied learning counts | Per-review learned flag and unique pattern keys |
| Merge lookup could match multiple commit records | Exact repository/PR/head identity |
| Evaluation used filename as evidence context | Labeled patch fixtures; no unsupported faithfulness claims |
| Windows/AWS-only onboarding | Offline Python demo and complete Docker stack |

## Service boundaries

- **Gateway:** public signed-event ingress only. No database credentials are needed by its code, though the starter manifests use a shared Secret for simplicity.
- **Webhook intake:** typed event validation, repository allowlist, durable review/job creation, protected history and retry endpoints.
- **Orchestrator:** serializes analysis for each review with PostgreSQL row locks, fetches and validates file patches, loads historical observations, runs the graph, stores results before calling publisher.
- **Publisher:** serializes publication, reconciles existing GitHub reviews, checks current head, posts commit-bound summaries/comments, records final state.
- **Learner:** serializes learning for the reviewed head and upserts recurring observation counts after merge. It does not train model weights.

## Job lifecycle

`pending → running → done`, or `running → pending → … → failed` after six attempts. Celery Beat dispatches the PostgreSQL outbox every ten seconds. Failed attempts use exponential backoff capped at five minutes. A ten-minute lease recovers abandoned running jobs; Celery's hard execution limit is shorter than that lease.

PostgreSQL is required for concurrent deployment. SQLite supports isolated tests and single-process experiments only; it does not implement the row-lock semantics required for multiple workers.

The publisher uses a unique marker plus matching App identity and head SHA to reconcile a successful GitHub POST whose local commit failed. This substantially reduces duplicate publication, but **exactly-once delivery across PostgreSQL and GitHub is not guaranteed**: GitHub offers no atomic transaction with this database, and API visibility races can still matter. Inspect exceptional retry cases before claiming exactly-once semantics.

The service holds database row locks during provider calls. This makes duplicate-job handling simple and correct at this project's scale; larger deployments should move to renewable leases and explicit operation fencing to avoid long database transactions.

## Review coverage and trust

Only added lines in complete textual patches are eligible. Deleted/binary/missing patches and files exceeding the configured budget produce coverage warnings. The entire PR is not necessarily reviewed. Exact same-message duplicates at the same location are removed across agents; semantic paraphrases may remain.

Repository code and historical observations are passed as untrusted user data. The model has no execution tools. Prompts prohibit following embedded instructions, and validated schemas/locations constrain publication. These controls do not establish that every model finding is correct. Human review remains necessary.

Learning stores observations from reviewed merged heads. It cannot determine whether developers accepted or fixed individual suggestions. These observations are never promoted to trusted system instructions.

The reference design mentions S3 report storage. Terraform provides an optional private bucket; runtime review data is stored in PostgreSQL and evaluation reports are local/CI artifacts. Automatic S3 archival is not enabled. Langfuse spans provide basic generation tracing; token-cost accounting and quality dashboards are future extensions.

## Operational boundaries

Kubernetes manifests are a deployable starting configuration, not proof of production readiness. Before public operation: use managed secrets, backup/restore drills, provider quotas, appropriate retention, private service networking, ingress controls, and production load tests. API metadata and health endpoints contain no review content; the intake data endpoints require service authentication.

The starter AWS shape uses one NAT gateway, one RDS instance, and one Redis node to keep the project understandable. It is not a highly available data tier. Choose multi-AZ options and sizing for real production requirements.

## Naming compatibility

The product is **DiffSentry — Multi-Agent GitHub Code Reviewer**, hosted at [MunwarMohammad/diffsentry](https://github.com/MunwarMohammad/diffsentry). Existing `pr-reviewer` infrastructure identifiers, dashboard UID, queue application name, and GitHub reconciliation markers are retained for compatibility with running installations and stored reviews.
