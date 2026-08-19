"""add outlines table

Revision ID: d3c2b1a09f8e
Revises: b9f142ca6cea
Create Date: 2026-08-20 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3c2b1a09f8e"
down_revision: str | Sequence[str] | None = "b9f142ca6cea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the versioned outline table.

    Idempotent: legacy-upgrade tests replay the chain from an earlier revision
    without dropping the outline table, so an existing table must be left
    untouched instead of failing CREATE. The workspace_id index is ensured
    separately so an interrupted first run cannot stamp the revision without
    the index the model metadata declares. The (workspace_id, version) unique
    constraint guards concurrent outline revisions and is ensured the same way.
    """
    inspector = sa.inspect(op.get_bind())
    if "outlines" not in inspector.get_table_names():
        op.create_table(
            "outlines",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("workspace_id", sa.String(length=32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("actor", sa.String(length=100), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "workspace_id",
                "version",
                name="uq_outlines_workspace_version",
            ),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_outlines_workspace_id "
        "ON outlines (workspace_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_outlines_workspace_version "
        "ON outlines (workspace_id, version)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_outlines_workspace_id"), table_name="outlines")
    op.drop_table("outlines")
