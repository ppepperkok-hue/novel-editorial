"""add memory decay columns

Revision ID: 5b5bdeb4ed9d
Revises: f80e112950a2
Create Date: 2026-08-18 19:38:50.400444

"""
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b5bdeb4ed9d"
down_revision: str | Sequence[str] | None = "f80e112950a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add strength / last_accessed_at / archived_at to agent_memories.

    SQLite rejects non-constant defaults (CURRENT_TIMESTAMP) in ALTER TABLE
    ADD COLUMN, so last_accessed_at backfills with a literal timestamp captured
    when this migration runs; ORM inserts always supply their own value.
    Each column is added only when missing so legacy-upgrade tests that replay
    the chain from an earlier revision (with agent_memories left in place) do
    not fail on duplicate columns.
    """
    backfill_ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    existing = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("agent_memories")
    }
    if "strength" not in existing:
        op.add_column(
            "agent_memories",
            sa.Column("strength", sa.Integer(), nullable=False, server_default=sa.text("100")),
        )
    if "last_accessed_at" not in existing:
        op.add_column(
            "agent_memories",
            sa.Column(
                "last_accessed_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text(f"'{backfill_ts}'"),
            ),
        )
    if "archived_at" not in existing:
        op.add_column(
            "agent_memories",
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("agent_memories", "archived_at")
    op.drop_column("agent_memories", "last_accessed_at")
    op.drop_column("agent_memories", "strength")
