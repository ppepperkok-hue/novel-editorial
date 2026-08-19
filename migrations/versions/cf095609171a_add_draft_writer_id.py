"""add draft writer id

Revision ID: cf095609171a
Revises: d3c2b1a09f8e
Create Date: 2026-08-20 01:27:09.604982

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cf095609171a"
down_revision: str | Sequence[str] | None = "d3c2b1a09f8e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add drafts.writer_id and backfill the default writer per workspace.

    Idempotent: legacy-upgrade tests replay the chain from an earlier revision
    without dropping the column, so an existing column must be left untouched
    instead of failing ALTER. Backfill only touches rows whose writer_id is
    still NULL, so replaying the migration cannot clobber explicit assignments.
    The backfill follows the same deterministic order as get_default_writer
    (oldest created_at, id tie-break); workspaces without a writer stay NULL.
    """
    inspector = sa.inspect(op.get_bind())
    if "drafts" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("drafts")}
        if "writer_id" not in columns:
            op.add_column(
                "drafts",
                sa.Column("writer_id", sa.String(length=32), nullable=True),
            )
        op.execute(
            "UPDATE drafts SET writer_id = ("
            "SELECT a.id FROM agents a "
            "WHERE a.workspace_id = drafts.workspace_id "
            "AND a.role = 'writer' "
            "ORDER BY a.created_at ASC, a.id ASC LIMIT 1"
            ") WHERE writer_id IS NULL"
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("drafts", "writer_id")
