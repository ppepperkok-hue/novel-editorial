"""add setting entries and versions

Revision ID: 92a0cb3a3bb1
Revises: 5b5bdeb4ed9d
Create Date: 2026-08-19 12:24:47.147751

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "92a0cb3a3bb1"
down_revision: str | Sequence[str] | None = "5b5bdeb4ed9d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create setting entries and versions tables.

    Idempotent: legacy-upgrade tests replay the chain from an earlier revision
    without dropping the setting tables, so tables that already exist must be
    left untouched instead of failing CREATE. Indexes are ensured separately so
    an interrupted first run cannot stamp the revision without the indexes the
    model metadata declares.
    """
    inspector = sa.inspect(op.get_bind())
    if "setting_versions" not in inspector.get_table_names():
        op.create_table(
            "setting_versions",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("entry_id", sa.String(length=32), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("actor", sa.String(length=100), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "entry_id", "version", name="uq_setting_versions_entry_version"
            ),
        )
    if "setting_entries" not in inspector.get_table_names():
        op.create_table(
            "setting_entries",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("workspace_id", sa.String(length=32), nullable=False),
            sa.Column("kind", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("source", sa.Text(), nullable=False),
            sa.Column("current_version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_setting_versions_entry_id "
        "ON setting_versions (entry_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_setting_entries_workspace_id "
        "ON setting_entries (workspace_id)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_setting_entries_workspace_id"), table_name="setting_entries")
    op.drop_table("setting_entries")
    op.drop_index(op.f("ix_setting_versions_entry_id"), table_name="setting_versions")
    op.drop_table("setting_versions")
