"""add inspirations table

Revision ID: 9833bf1054ab
Revises: cf095609171a
Create Date: 2026-08-22 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9833bf1054ab"
down_revision: str | Sequence[str] | None = "cf095609171a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the inspirations table and its workspace index.

    Idempotent: legacy-upgrade tests replay the chain from an earlier
    revision without dropping the inspirations table, so a table that already
    exists must be left untouched instead of failing CREATE. The index is
    ensured separately so an interrupted first run cannot stamp the revision
    without the index the model metadata declares.
    """
    inspector = sa.inspect(op.get_bind())
    if "inspirations" not in inspector.get_table_names():
        op.create_table(
            "inspirations",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("workspace_id", sa.String(length=32), nullable=False),
            sa.Column(
                "kind", sa.String(length=20), nullable=False, server_default="灵感"
            ),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("source", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_inspirations_workspace_id "
        "ON inspirations (workspace_id)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_inspirations_workspace_id"), table_name="inspirations")
    op.drop_table("inspirations")
