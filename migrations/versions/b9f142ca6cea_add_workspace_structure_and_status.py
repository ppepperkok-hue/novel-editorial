"""add workspace structure and status

Revision ID: b9f142ca6cea
Revises: 8030d420636d
Create Date: 2026-08-20 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9f142ca6cea"
down_revision: str | Sequence[str] | None = "8030d420636d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the structure tree table and a workspace progress status column.

    Idempotent: legacy-upgrade tests replay the chain from an earlier revision
    without dropping the structure table, so an existing table must be left
    untouched instead of failing CREATE. The workspace_id index is ensured
    separately so an interrupted first run cannot stamp the revision without
    the index the model metadata declares. The workspaces.status column is
    added only when missing and existing rows are backfilled to writing.
    """
    inspector = sa.inspect(op.get_bind())
    if "workspace_structure_nodes" not in inspector.get_table_names():
        op.create_table(
            "workspace_structure_nodes",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("workspace_id", sa.String(length=32), nullable=False),
            sa.Column("parent_id", sa.String(length=32), nullable=True),
            sa.Column("kind", sa.String(length=10), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("draft_id", sa.String(length=32), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["parent_id"], ["workspace_structure_nodes.id"]
            ),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workspace_structure_nodes_workspace_id "
        "ON workspace_structure_nodes (workspace_id)"
    )
    status_column = "status" in {
        column["name"] for column in inspector.get_columns("workspaces")
    }
    if not status_column:
        op.add_column(
            "workspaces",
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="writing",
            ),
        )
        op.execute("UPDATE workspaces SET status = 'writing'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_workspace_structure_nodes_workspace_id"),
        table_name="workspace_structure_nodes",
    )
    op.drop_table("workspace_structure_nodes")
    op.drop_column("workspaces", "status")
