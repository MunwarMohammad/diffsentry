# Token usage, estimated costs and per-commit reviews

## Review identity

DiffSentry stores one review for each `(repository, PR number, head SHA)`. A repeated webhook for the same SHA is deduplicated. A new commit queues a new review; comments are attached to that specific SHA. This behavior is intentional: feedback on an earlier commit does not prove a later change is correct. Tests cover duplicate delivery, new-head creation, exact-head merge learning, and stale-head rejection.

## Usage accounting

Each live agent call records its returned model, requested model, response ID, response status, input tokens, cached input tokens and output tokens. Four successful parallel agents produce four generation rows. Demo rules generate no synthetic token usage.

Usage is committed independently of the analysis transaction. Responses that are incomplete/refused are recorded before validation fails; subsequent retries add their own response records. A unique response ID prevents recording the same returned response twice. Connection errors are recorded with unknown tokens. No source code, prompt, private key or response content is stored in the usage ledger.

The generations table intentionally uses a review identifier without a foreign-key lock: the parent analysis transaction holds the review row lock while four agents run, and usage must survive its rollback. Identifiers are supplied by the orchestrator, not by repository content.

## Configure estimated prices

Set `OPENAI_PRICING` in your ignored `.env` to a JSON object keyed by model, with USD prices **per million tokens**. Each model requires `input_per_million`, `cached_input_per_million` and `output_per_million`. Verify your model's current standard-tier rates using [OpenAI pricing](https://developers.openai.com/api/docs/pricing); private discounts and alternative service tiers may differ.

Example syntax, using illustrative prices and a fictional model:

```dotenv
OPENAI_PRICING='{"my-model":{"input_per_million":2,"cached_input_per_million":0.5,"output_per_million":8}}'
```

The estimate is:

```text
((input_tokens - cached_tokens) × input_rate
 + cached_tokens × cached_rate
 + output_tokens × output_rate) / 1,000,000
```

The rate snapshot is saved with each generation, so later configuration edits do not rewrite historical costs. A returned dated snapshot can use its requested alias's configured rate. Other models and nonstandard service tiers remain unpriced unless supported by the estimator. Missing rates, missing cache details and invalid usage produce `null` cost, not zero.

These values estimate observed responses, not an exact invoice. OpenAI SDK retries that never yield a response, transport failures, billing adjustments and discounted agreements may create differences. Output tokens already include reasoning usage reported by the Responses API; do not add reasoning tokens again.

## Inspect usage

The protected endpoint `GET /reviews/REVIEW_ID/usage` accepts the same bearer token as review history. It returns per-agent generations and a summary with token totals, calls lacking usage, calls lacking prices, known estimated cost subtotal, and a complete total only when every observed call is priced.

`estimated_cost_usd=null` and `cost_complete=false` mean that a complete cost is unavailable. Token totals sum only provider-reported values; check `calls_without_usage` before treating them as complete.

## Langfuse and Grafana

With Langfuse enabled, a review creates a parent trace span with child agent generations. Each generation receives non-overlapping uncached input, cached input and output buckets plus the configured cost estimate when available. Langfuse may also infer prices using its own configured model definitions; those can differ from the locally configured estimate. See [Langfuse usage and cost tracking](https://langfuse.com/docs/observability/features/token-and-cost-tracking).

Prometheus's intake scrape exposes persisted metrics across workers:

- `diffsentry_llm_tokens{agent,model,type}` — input, cached input (subset of input), and output.
- `diffsentry_llm_estimated_cost_usd{agent,model}` — known estimated cost subtotal.
- `diffsentry_llm_unpriced_calls{agent,model}` — observed calls lacking an estimate.

The provisioned Grafana dashboard has token, known-cost and unpriced-call panels. Do not add cached input to total input; it is already included in the provider's input count.

## Verification scope

Run `docker compose exec -T orchestrator python -m scripts.check_usage` for the PostgreSQL integration check in a disposable schema with a held parent review lock. It makes no real provider calls.

Automated tests use mocked OpenAI Responses and Langfuse observations to verify accounting, cache discounts, incomplete responses, rate snapshots, idempotency, four-agent aggregation, authentication, metrics, and unknown-cost handling. Live OpenAI/GitHub review execution and external Langfuse ingestion require configured account credentials and a real sandbox PR. A passing mock test does not establish live provider behavior.
