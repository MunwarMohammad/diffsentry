import pytest

from reviewer.config import get_settings
from reviewer.database import engine
from reviewer.models import Base


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("REVIEW_MODE", "demo")
    monkeypatch.setenv("PUBLISH_REVIEWS", "false")
    monkeypatch.setenv("INTERNAL_API_TOKEN", "test-internal-token")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setenv("ALLOWED_REPOSITORIES", "demo/example")
    get_settings.cache_clear()
    engine.cache_clear()
    Base.metadata.create_all(engine())
    yield
    engine().dispose()
    engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
def auth():
    return {"Authorization": "Bearer test-internal-token"}


@pytest.fixture
def event():
    return {
        "action": "opened",
        "repository": {"full_name": "demo/example"},
        "installation": {"id": 1},
        "pull_request": {"number": 1, "head": {"sha": "a" * 40}, "merged": False},
    }
