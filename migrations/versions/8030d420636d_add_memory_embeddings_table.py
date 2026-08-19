"""add memory embeddings table

Revision ID: 8030d420636d
Revises: 92a0cb3a3bb1
Create Date: 2026-08-19 13:40:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8030d420636d"
down_revision: str | Sequence[str] | None = "92a0cb3a3bb1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the memory embeddings table.

    Idempotent: legacy-upgrade tests replay the chain from an earlier revision
    without dropping the embedding table, so a table that already exists must
    be left untouched instead of failing CREATE. The workspace_id index is
    ensured separately so an interrupted first run cannot stamp the revision
    without the index the model metadata declares.
    """
    inspector = sa.inspect(op.get_bind())
    if "memory_embeddings" not in inspector.get_table_names():
        op.create_table(
            "memory_embeddings",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("workspace_id", sa.String(length=32), nullable=False),
            sa.Column("layer", sa.String(length=50), nullable=False),
            sa.Column("source_id", sa.String(length=32), nullable=False),
            sa.Column("vector", sa.Text(), nullable=False),
            sa.Column("dim", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "layer", "source_id", name="uq_memory_embeddings_layer_source"
            ),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_memory_embeddings_workspace_id "
        "ON memory_embeddings (workspace_id)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_memory_embeddings_workspace_id"), table_name="memory_embeddings"
    )
    op.drop_table("memory_embeddings")
