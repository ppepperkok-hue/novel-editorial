"""add agent motives and personality params

Revision ID: c1557045673c
Revises: 9833bf1054ab
Create Date: 2026-08-23 01:21:45.206438

"""
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1557045673c"
down_revision: str | Sequence[str] | None = "9833bf1054ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create agent_motives and add four personality-param columns to agents.

    Both steps are idempotent: legacy-upgrade tests replay the chain from an
    earlier revision while the table/columns may already exist, so existing
    schema (and any data in it) must be left untouched instead of failing on
    duplicate CREATE/ADD. Timestamp defaults use a literal captured when this
    migration runs, matching the N17 memory-decay migration's SQLite-safe
    backfill style; ORM inserts always supply their own values.
    """
    backfill_ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    if "agent_motives" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "agent_motives",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("workspace_id", sa.String(length=32), nullable=False),
            sa.Column("agent_id", sa.String(length=32), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column(
                "strength", sa.Integer(), nullable=False, server_default=sa.text("100")
            ),
            sa.Column(
                "source", sa.String(length=200), nullable=False, server_default=""
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text(f"'{backfill_ts}'"),
            ),
            sa.Column(
                "last_touched_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text(f"'{backfill_ts}'"),
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_motives_workspace_id "
        "ON agent_motives (workspace_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_motives_agent_id "
        "ON agent_motives (agent_id)"
    )
    agent_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("agents")
    }
    for field in ("proactivity", "stubbornness", "talkativeness", "patience"):
        if field not in agent_columns:
            op.add_column(
                "agents",
                sa.Column(
                    field, sa.Integer(), nullable=False, server_default=sa.text("5")
                ),
            )
    # Backfill per-role defaults; must match ROLE_PERSONALITY_PARAMS in
    # store/models.py (editor_in_chief / editor / writer / reviewer).
    op.execute(
        "UPDATE agents SET proactivity=6, stubbornness=7, talkativeness=4, patience=8 "
        "WHERE role='editor_in_chief'"
    )
    op.execute(
        "UPDATE agents SET proactivity=8, stubbornness=6, talkativeness=7, patience=3 "
        "WHERE role='editor'"
    )
    op.execute(
        "UPDATE agents SET proactivity=5, stubbornness=6, talkativeness=5, patience=4 "
        "WHERE role='writer'"
    )
    op.execute(
        "UPDATE agents SET proactivity=4, stubbornness=8, talkativeness=3, patience=7 "
        "WHERE role='reviewer'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_agent_motives_agent_id"), table_name="agent_motives")
    op.drop_index(op.f("ix_agent_motives_workspace_id"), table_name="agent_motives")
    op.drop_table("agent_motives")
    op.drop_column("agents", "patience")
    op.drop_column("agents", "talkativeness")
    op.drop_column("agents", "stubbornness")
    op.drop_column("agents", "proactivity")
