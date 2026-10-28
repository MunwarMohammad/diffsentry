import pytest
from pydantic import ValidationError

from reviewer.config import Settings


def test_production_rejects_demo_secrets_and_modes():
    with pytest.raises(ValidationError):
        Settings(environment="production")
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            github_webhook_secret="a" * 32,
            internal_api_token="b" * 32,
            review_mode="demo",
        )
    with pytest.raises(ValidationError):
        Settings(publish_reviews=True, review_mode="demo")


def test_production_configuration_and_allowlist():
    settings = Settings(
        environment="production",
        github_webhook_secret="a" * 32,
        internal_api_token="b" * 32,
        review_mode="live",
        allowed_repositories="demo/example, other/repo",
    )
    assert settings.permits("DEMO/EXAMPLE")
    assert not settings.permits("unlisted/repo")
