"""add unique constraint on agent motives source

Revision ID: 6ebe40261d2545fe
Revises: c1557045673c
Create Date: 2026-08-23 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6ebe40261d2545fe"
down_revision: str | Sequence[str] | None = "c1557045673c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _unique_source_index_exists(bind) -> bool:
    """True when a unique index covers (workspace_id, agent_id, kind, source).

    SQLite may surface the constraint as a named index or as a
    ``sqlite_autoindex_agent_motives_*`` row when it is declared inline in a
    recreated table, so name matching alone is unreliable; compare columns.
    """
    for row in bind.exec_driver_sql('PRAGMA index_list("agent_motives")').fetchall():
        if not row[2]:
            continue
        columns = [
            column[2]
            for column in bind.exec_driver_sql(
                f'PRAGMA index_info("{row[1]}")'
            ).fetchall()
        ]
        if columns[:4] == ["workspace_id", "agent_id", "kind", "source"]:
            return True
    return False


def upgrade() -> None:
    """Deduplicate agent_motives, then enforce one motive per source.

    The keeper per (workspace_id, agent_id, kind, source) group is the
    earliest-created row (created_at, then id as tie-break); the rest are
    deleted. Rationale: the first row is the canonical "one thing" record -
    its content is the original one and its strength is the row's own value,
    so nothing is fabricated, unlike merging strengths into a new number.
    Idempotent: legacy-replay tests rerun the chain with the table and the
    constraint already in place, so dedupe must be a no-op on clean data and
    constraint creation must be skipped when the unique source index already
    exists (named or autoindex).
    """
    bind = op.get_bind()
    if "agent_motives" not in sa.inspect(bind).get_table_names():
        return
    op.execute(
        """
        DELETE FROM agent_motives
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY workspace_id, agent_id, kind, source
                    ORDER BY created_at, id
                ) AS rn
                FROM agent_motives
            ) WHERE rn > 1
        )
        """
    )
    if not _unique_source_index_exists(bind):
        with op.batch_alter_table("agent_motives") as batch_op:
            batch_op.create_unique_constraint(
                "uq_agent_motives_workspace_agent_kind_source",
                ["workspace_id", "agent_id", "kind", "source"],
            )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("agent_motives") as batch_op:
        batch_op.drop_constraint(
            "uq_agent_motives_workspace_agent_kind_source", type_="unique"
        )
