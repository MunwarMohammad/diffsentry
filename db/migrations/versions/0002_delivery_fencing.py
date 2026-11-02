"""Fence duplicate deliveries and record archive destinations."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("lease_token", sa.String(36), nullable=True))
    op.add_column("reviews", sa.Column("archive_uri", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("reviews", "archive_uri")
    op.drop_column("jobs", "lease_token")
