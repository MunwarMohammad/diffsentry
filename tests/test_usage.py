import asyncio
from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from reviewer.config import TokenRates, get_settings
from reviewer.database import session
from reviewer.graph import review_files, run_agent
from reviewer.models import AgentOutput, Generation, Review
from reviewer.usage import langfuse_details, persist_usage, usage_data, usage_summary
from services.webhook.main import app


def response(**changes):
    values = {
        "id": "resp_test",
        "model": "test-model",
        "status": "completed",
        "service_tier": "default",
        "output_parsed": AgentOutput(findings=[]),
        "usage": SimpleNamespace(
            input_tokens=1000,
            output_tokens=100,
            input_tokens_details=SimpleNamespace(cached_tokens=400),
        ),
    }
    return SimpleNamespace(**(values | changes))


def pricing():
    settings = get_settings()
    settings.openai_model = "test-model"
    settings.openai_pricing = {
        "test-model": TokenRates(
            input_per_million="2", cached_input_per_million="0.5", output_per_million="8"
        )
    }


def test_cached_tokens_are_not_double_counted():
    pricing()
    data = usage_data(response(), "security")
    assert data["estimated_cost_usd"] == Decimal("0.0022")
    details = langfuse_details(data)
    assert details["usage_details"] == {"input": 600, "cache_read_input_tokens": 400, "output": 100}
    assert details["cost_details"] == {"total": 0.0022}
    assert data["rates"]["input_per_million"] == "2"


@pytest.mark.parametrize(
    "overrides",
    [
        {"usage": None},
        {"model": "unknown-model"},
        {"service_tier": "priority"},
        {"usage": SimpleNamespace(input_tokens=100, output_tokens=10, input_tokens_details=None)},
        {
            "usage": SimpleNamespace(
                input_tokens=100,
                output_tokens=10,
                input_tokens_details=SimpleNamespace(cached_tokens=200),
            )
        },
    ],
)
def test_unknown_or_invalid_cost_is_not_reported_as_zero(overrides):
    pricing()
    assert usage_data(response(**overrides), "security")["estimated_cost_usd"] is None


def test_no_configured_prices_and_empty_ledger_remain_unknown():
    assert usage_data(response(), "security")["estimated_cost_usd"] is None
    summary = usage_summary([])
    assert summary["estimated_cost_usd"] is None and summary["cost_complete"] is False


def test_ledger_response_id_is_idempotent_and_snapshots_rates():
    pricing()
    data = usage_data(response(), "security")
    persist_usage("a" * 36, data)
    persist_usage("a" * 36, data)
    get_settings().openai_pricing = {}
    with session() as db:
        rows = db.scalars(select(Generation)).all()
        assert len(rows) == 1
        assert rows[0].estimated_cost_usd == Decimal("0.0022")
        assert rows[0].rates["output_per_million"] == "8"


def test_partial_totals_expose_unpriced_calls():
    pricing()
    persist_usage("a" * 36, usage_data(response(), "security"))
    persist_usage("a" * 36, usage_data(None, "style", status="APIConnectionError"))
    with session() as db:
        result = usage_summary(db.scalars(select(Generation)))
    assert result["calls"] == 2
    assert result["calls_without_cost"] == result["calls_without_usage"] == 1
    assert Decimal(result["known_estimated_cost_usd"]) == Decimal("0.0022")
    assert result["estimated_cost_usd"] is None


def test_live_call_updates_langfuse_and_persists_refusal_usage():
    pricing()
    settings = get_settings()
    settings.review_mode, settings.openai_api_key, settings.langfuse_enabled = (
        "live",
        "test-only",
        True,
    )
    client = AsyncMock()
    client.responses.parse.return_value = response(status="incomplete", output_parsed=None)
    generation = Mock()
    with (
        patch("reviewer.graph.AsyncOpenAI") as constructor,
        patch("langfuse.get_client") as langfuse,
    ):
        constructor.return_value.__aenter__.return_value = client
        langfuse.return_value.start_as_current_observation.return_value = nullcontext(generation)
        with pytest.raises(RuntimeError, match="incomplete"):
            asyncio.run(run_agent("security", [], [], review_id="a" * 36))
    assert generation.update.call_args.kwargs["usage_details"]["input"] == 600
    with session() as db:
        row = db.scalar(select(Generation))
        assert row.status == "incomplete" and row.input_tokens == 1000


def test_four_live_agents_produce_four_usage_records():
    pricing()
    settings = get_settings()
    settings.review_mode, settings.openai_api_key = "live", "test-only"
    client = AsyncMock()
    counter = iter(range(4))

    async def parsed(**kwargs):
        return response(id=f"resp_{next(counter)}")

    client.responses.parse.side_effect = parsed
    with patch("reviewer.graph.AsyncOpenAI") as constructor:
        constructor.return_value.__aenter__.return_value = client
        asyncio.run(review_files([], review_id="a" * 36))
    with session() as db:
        rows = db.scalars(select(Generation)).all()
        assert len(rows) == 4
        assert len({r.agent for r in rows}) == 4
        assert usage_summary(rows)["input_tokens"] == 4000


def test_usage_api_requires_auth_and_metrics_expose_cost(auth):
    pricing()
    with session() as db:
        review = Review(repo="demo/example", number=1, head_sha="a" * 40, installation_id=1)
        db.add(review)
        db.commit()
        review_id = review.id
    persist_usage(review_id, usage_data(response(), "security"))
    with TestClient(app) as client:
        assert client.get(f"/reviews/{review_id}/usage").status_code == 401
        result = client.get(f"/reviews/{review_id}/usage", headers=auth).json()
        assert result["head_sha"] == "a" * 40
        assert result["summary"]["cost_complete"] is True
        assert result["generations"][0]["rates"] is not None
        metrics = client.get("/queue-metrics").text
        assert "diffsentry_llm_tokens" in metrics and "diffsentry_llm_estimated_cost_usd" in metrics


def test_demo_does_not_invent_provider_usage():
    asyncio.run(review_files([], review_id="a" * 36))
    with session() as db:
        assert db.scalar(select(Generation)) is None
