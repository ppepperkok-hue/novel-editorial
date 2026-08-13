"""add events table

Revision ID: 1ecd3fdf59e1
Revises: 98fd820d7e77
Create Date: 2026-08-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1ecd3fdf59e1"
down_revision: str | Sequence[str] | None = "98fd820d7e77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "events",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_events_workspace_id"), "events", ["workspace_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_events_workspace_id"), table_name="events")
    op.drop_table("events")
