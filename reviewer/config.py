from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: Literal["local", "production"] = "local"
    database_url: str = "sqlite:///reviewer.db"
    redis_url: str = "redis://localhost:6379/0"
    github_webhook_secret: str = "local-demo-webhook-secret"
    internal_api_token: str = "local-demo-internal-token"
    github_app_id: str = ""
    github_app_private_key: str = ""
    github_app_private_key_path: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    review_mode: Literal["demo", "live"] = "demo"
    publish_reviews: bool = False
    allowed_repositories: str = ""
    webhook_url: str = "http://localhost:8001"
    orchestrator_url: str = "http://localhost:8002"
    publisher_url: str = "http://localhost:8003"
    learner_url: str = "http://localhost:8004"
    max_webhook_bytes: int = Field(default=2_000_000, gt=0)
    max_diff_chars: int = Field(default=100_000, gt=0)
    max_findings: int = Field(default=30, ge=1, le=50)
    langfuse_enabled: bool = False

    @model_validator(mode="after")
    def secure_production(self):
        if self.environment == "production":
            for name in ("github_webhook_secret", "internal_api_token"):
                value = getattr(self, name)
                if len(value) < 32 or value.startswith("local-demo"):
                    raise ValueError(f"{name} must be a unique secret of at least 32 characters")
            if self.review_mode != "live" or not self.allowed_repositories.strip():
                raise ValueError(
                    "Production requires live mode and an explicit repository allowlist"
                )
        if self.publish_reviews and self.review_mode != "live":
            raise ValueError("Demo findings cannot be published to GitHub")
        return self

    def private_key(self) -> str:
        if self.github_app_private_key_path:
            return Path(self.github_app_private_key_path).read_text()
        return self.github_app_private_key.replace("\\n", "\n")

    def permits(self, repo: str) -> bool:
        allowed = {s.strip().lower() for s in self.allowed_repositories.split(",") if s.strip()}
        return not allowed or repo.lower() in allowed


@lru_cache
def get_settings() -> Settings:
    return Settings()
