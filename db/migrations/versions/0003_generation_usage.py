"""Persist provider-reported usage and auditable estimated costs."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "generations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("review_id", sa.String(36), nullable=False),
        sa.Column("agent", sa.String(50), nullable=False),
        sa.Column("requested_model", sa.String(150), nullable=False),
        sa.Column("model", sa.String(150), nullable=False),
        sa.Column("response_id", sa.String(150), nullable=True, unique=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(20, 12), nullable=True),
        sa.Column("rates", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_generations_review_id", "generations", ["review_id"])


def downgrade():
    op.drop_table("generations")
