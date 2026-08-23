"""add agent drift columns

Revision ID: 0b7aeb265bb2
Revises: 6ebe40261d2545fe
Create Date: 2026-08-23 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0b7aeb265bb2"
down_revision: str | Sequence[str] | None = "6ebe40261d2545fe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Drift columns must match DRIFT_PARAM_FIELDS in store/models.py.
DRIFT_COLUMNS: tuple[str, ...] = (
    "drift_proactivity",
    "drift_stubbornness",
    "drift_talkativeness",
    "drift_patience",
)


def upgrade() -> None:
    """Add four drift columns to agents, backfilling existing rows with 0.

    Each column is added only when missing so legacy-upgrade tests that replay
    the chain (with the columns already in place) do not fail on duplicate ADD
    COLUMN. SQLite fills existing rows with the server default on ADD COLUMN,
    so old rows are backfilled to 0; the explicit UPDATE is a belt-and-braces
    no-op that keeps the backfill visible and deterministic on any dialect.
    """
    existing = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("agents")
    }
    for field in DRIFT_COLUMNS:
        if field not in existing:
            op.add_column(
                "agents",
                sa.Column(field, sa.Integer(), nullable=False, server_default=sa.text("0")),
            )
    for field in DRIFT_COLUMNS:
        op.execute(f"UPDATE agents SET {field}=0 WHERE {field} IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    for field in DRIFT_COLUMNS:
        op.drop_column("agents", field)
