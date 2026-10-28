import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(UTC)


def uid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("repo", "number", "head_sha"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    repo: Mapped[str] = mapped_column(String(250))
    number: Mapped[int] = mapped_column(Integer)
    head_sha: Mapped[str] = mapped_column(String(64))
    installation_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    findings: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    github_review_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    learned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("review_id", "kind"),
        Index("ix_jobs_dispatch", "status", "available_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id"))
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_error: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Pattern(Base):
    __tablename__ = "patterns"
    __table_args__ = (UniqueConstraint("repo", "pattern_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    repo: Mapped[str] = mapped_column(String(250))
    pattern_key: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    frequency: Mapped[int] = mapped_column(Integer, default=1)


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: str = Field(min_length=1, max_length=500)
    line: int = Field(ge=1)
    severity: Literal["info", "warning", "error"]
    message: str = Field(min_length=1, max_length=1500)
    agent: str = ""


class AgentFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: str
    line: int
    severity: Literal["info", "warning", "error"]
    message: str


class AgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    findings: list[AgentFinding]


class ReviewRequest(BaseModel):
    review_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
