"""Docker/PostgreSQL accounting check with mocked providers and an isolated schema."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, text

from reviewer.config import TokenRates, get_settings
from reviewer.database import engine, session
from reviewer.graph import review_files
from reviewer.models import Base, Generation, Review
from reviewer.usage import usage_summary


def main():
    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        raise SystemExit("Run this check inside Docker's orchestrator service")
    original = engine()
    schema = "diffsentry_usage_test_" + uuid.uuid4().hex
    with original.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated = original.execution_options(schema_translate_map={None: schema})
    try:
        with patch("reviewer.database.engine", return_value=isolated):
            Base.metadata.create_all(isolated)
            settings.review_mode, settings.openai_api_key = "live", "mock-only"
            settings.langfuse_enabled = False
            settings.openai_model = "mock-accounting-model"
            settings.openai_pricing = {
                settings.openai_model: TokenRates(
                    input_per_million="2", cached_input_per_million="0.5", output_per_million="8"
                )
            }
            with session() as db:
                review = Review(
                    repo="demo/accounting-check", number=1, head_sha="a" * 40, installation_id=1
                )
                db.add(review)
                db.commit()
                review_id = review.id
            mock = AsyncMock()

            async def response(**kwargs):
                return SimpleNamespace(
                    id="mock_" + uuid.uuid4().hex,
                    model=settings.openai_model,
                    status="completed",
                    service_tier="default",
                    output_parsed=SimpleNamespace(findings=[]),
                    usage=SimpleNamespace(
                        input_tokens=1000,
                        output_tokens=100,
                        input_tokens_details=SimpleNamespace(cached_tokens=400),
                    ),
                )

            mock.responses.parse.side_effect = response
            with session() as parent, patch("reviewer.graph.AsyncOpenAI") as sdk:
                sdk.return_value.__aenter__.return_value = mock
                parent.scalar(select(Review).where(Review.id == review_id).with_for_update())
                # The usage writes must not deadlock against the held parent lock.
                asyncio.run(asyncio.wait_for(review_files([], review_id=review_id), timeout=20))
                parent.rollback()
            with session() as db:
                result = usage_summary(db.scalars(select(Generation)))
                assert result["calls"] == 4 and result["input_tokens"] == 4000
                assert float(result["estimated_cost_usd"]) == 0.0088
                assert result["cost_complete"] is True
            print(
                "PASS: four mocked agent calls persisted usage to PostgreSQL while the parent review was locked; accounting survived rollback."
            )
            print("Isolated schema removed afterward. No real provider call or billing occurred.")
    finally:
        with original.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


if __name__ == "__main__":
    main()
