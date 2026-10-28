"""Initial review, outbox and learning schema."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("repo", sa.String(250), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("head_sha", sa.String(64), nullable=False),
        sa.Column("installation_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("github_review_id", sa.String(50), nullable=True),
        sa.Column("learned", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("repo", "number", "head_sha"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("review_id", sa.String(36), sa.ForeignKey("reviews.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(100), nullable=True),
        sa.UniqueConstraint("review_id", "kind"),
    )
    op.create_table(
        "patterns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("repo", sa.String(250), nullable=False),
        sa.Column("pattern_key", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("frequency", sa.Integer(), nullable=False),
        sa.UniqueConstraint("repo", "pattern_key"),
    )
    op.create_index("ix_jobs_dispatch", "jobs", ["status", "available_at"])


def downgrade():
    op.drop_table("patterns")
    op.drop_table("jobs")
    op.drop_table("reviews")
