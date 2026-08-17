"""add behavior timeline table

Revision ID: f80e112950a2
Revises: 9c3a71b5d2e4
Create Date: 2026-08-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f80e112950a2"
down_revision: str | Sequence[str] | None = "9c3a71b5d2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the append-only behavior timeline table.

    Idempotent: legacy-upgrade tests replay the chain from an earlier revision
    without dropping behavior_timeline, so a table that already exists must be
    left untouched instead of failing CREATE.
    """
    inspector = sa.inspect(op.get_bind())
    if "behavior_timeline" in inspector.get_table_names():
        return
    op.create_table(
        "behavior_timeline",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("agent_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("target", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("before_value", sa.Text(), nullable=True),
        sa.Column("after_value", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_behavior_timeline_workspace_id"),
        "behavior_timeline",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_behavior_timeline_agent_id"),
        "behavior_timeline",
        ["agent_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the behavior timeline table."""
    op.drop_index(op.f("ix_behavior_timeline_agent_id"), table_name="behavior_timeline")
    op.drop_index(op.f("ix_behavior_timeline_workspace_id"), table_name="behavior_timeline")
    op.drop_table("behavior_timeline")
