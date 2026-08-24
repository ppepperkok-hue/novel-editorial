"""add draft version actor

Revision ID: 75adac12d66d
Revises: 0b7aeb265bb2
Create Date: 2026-08-25 02:57:08.896679

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "75adac12d66d"
down_revision: str | Sequence[str] | None = "0b7aeb265bb2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add draft_versions.actor and backfill it from the owning draft writer.

    Idempotent: legacy-upgrade tests replay the chain from an earlier revision
    without dropping the column, so an existing column must be left untouched
    instead of failing ALTER. Backfill only touches rows whose actor is still
    empty, so replaying the migration cannot clobber later author-written
    versions (actor = "作者") or explicit assignments. The writer name comes
    from draft_versions.draft_id -> drafts.writer_id -> agents.name; rows
    without a writer (or with an unresolvable one) stay empty.
    """
    inspector = sa.inspect(op.get_bind())
    if "draft_versions" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("draft_versions")}
        if "actor" not in columns:
            op.add_column(
                "draft_versions",
                sa.Column(
                    "actor",
                    sa.String(length=100),
                    nullable=False,
                    server_default="",
                ),
            )
        op.execute(
            "UPDATE draft_versions SET actor = COALESCE(("
            "SELECT a.name FROM drafts d JOIN agents a ON a.id = d.writer_id "
            "WHERE d.id = draft_versions.draft_id"
            "), '') WHERE actor IS NULL OR actor = ''"
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("draft_versions", "actor")
