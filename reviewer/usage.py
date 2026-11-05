"""Provider usage accounting. Missing usage or prices remain unknown, never zero."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from reviewer.config import get_settings
from reviewer.database import session
from reviewer.models import Generation


def usage_data(response, agent, *, status=None):
    settings = get_settings()
    usage = getattr(response, "usage", None)
    model = getattr(response, "model", None) or settings.openai_model
    details = getattr(usage, "input_tokens_details", None)
    tokens_in = getattr(usage, "input_tokens", None)
    cached = getattr(details, "cached_tokens", None)
    tokens_out = getattr(usage, "output_tokens", None)
    # SDK schemas provide both breakdown and totals; absent details mean unknown
    # cache pricing, not a presumed uncached call.
    valid = all(type(n) is int and n >= 0 for n in (tokens_in, cached, tokens_out))
    valid = valid and cached <= tokens_in
    rates = settings.openai_pricing.get(model)
    if rates is None and (
        model == settings.openai_model or model.startswith(settings.openai_model + "-")
    ):
        rates = settings.openai_pricing.get(settings.openai_model)
    tier = getattr(response, "service_tier", None)
    if tier not in (None, "default", "auto"):
        rates = None  # Custom/priority/flex pricing requires separate verification.
    cost = None
    rate_snapshot = None
    if valid and rates is not None:
        cost = (
            Decimal(tokens_in - cached) * rates.input_per_million
            + Decimal(cached) * rates.cached_input_per_million
            + Decimal(tokens_out) * rates.output_per_million
        ) / Decimal(1_000_000)
        rate_snapshot = rates.model_dump(mode="json")
    return {
        "agent": agent,
        "requested_model": settings.openai_model,
        "model": model,
        "response_id": getattr(response, "id", None),
        "status": status or getattr(response, "status", None) or "error",
        "input_tokens": tokens_in if type(tokens_in) is int and tokens_in >= 0 else None,
        "cached_input_tokens": cached if valid else None,
        "output_tokens": tokens_out if type(tokens_out) is int and tokens_out >= 0 else None,
        "estimated_cost_usd": cost,
        "rates": rate_snapshot,
    }


def persist_usage(review_id, data):
    if review_id is None:
        return
    with session() as db:
        db.add(Generation(review_id=review_id, **data))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if data["response_id"] and db.scalar(
                select(Generation.id).where(Generation.response_id == data["response_id"])
            ):
                return
            raise


def usage_summary(rows):
    rows = list(rows)

    def total(name):
        return sum(getattr(r, name) or 0 for r in rows)

    priced = [r for r in rows if r.estimated_cost_usd is not None]
    all_priced = bool(rows) and len(priced) == len(rows)
    known_cost = sum((r.estimated_cost_usd for r in priced), Decimal(0))
    return {
        "calls": len(rows),
        "input_tokens": total("input_tokens"),
        "cached_input_tokens": total("cached_input_tokens"),
        "output_tokens": total("output_tokens"),
        "calls_without_usage": sum(r.input_tokens is None or r.output_tokens is None for r in rows),
        "calls_without_cost": len(rows) - len(priced),
        "known_estimated_cost_usd": str(known_cost),
        "estimated_cost_usd": str(known_cost) if all_priced else None,
        "cost_complete": all_priced,
        "scope": "Observed API responses only; excludes unreported SDK retries and provider billing adjustments.",
    }


def langfuse_details(data):
    details = {}
    if data["input_tokens"] is not None and data["cached_input_tokens"] is not None:
        details["input"] = data["input_tokens"] - data["cached_input_tokens"]
        details["cache_read_input_tokens"] = data["cached_input_tokens"]
    elif data["input_tokens"] is not None:
        details["input"] = data["input_tokens"]
    if data["output_tokens"] is not None:
        details["output"] = data["output_tokens"]
    cost = data["estimated_cost_usd"]
    return {
        "model": data["model"],
        "usage_details": details,
        **({"cost_details": {"total": float(cost)}} if cost is not None else {}),
    }
