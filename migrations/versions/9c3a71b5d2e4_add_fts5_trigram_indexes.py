"""add fts5 trigram full-text indexes for content layers

Revision ID: 9c3a71b5d2e4
Revises: 1ecd3fdf59e1
Create Date: 2026-08-14 20:30:00.000000

"""

import sys
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c3a71b5d2e4"
down_revision: str | Sequence[str] | None = "1ecd3fdf59e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (shadow table, source table) pairs for every long-text search layer.
# `id` stays UNINDEXED so a MATCH hit can join back to the source row; the
# shadow rowid mirrors the source rowid so triggers stay O(1) on sync.
_FTS_LAYERS: tuple[tuple[str, str], ...] = (
    ("message_fts", "messages"),
    ("review_fts", "reviews"),
    ("draft_version_fts", "draft_versions"),
    ("agent_memory_fts", "agent_memories"),
    ("plot_thread_fts", "plot_threads"),
)

_FTS5_WARNING = (
    "warning: this SQLite build does not include FTS5; skipping trigram "
    "full-text indexes (case-insensitive LIKE search remains available)"
)


def _fts5_available(connection: Any) -> bool:
    """Return True when this SQLite build was compiled with FTS5 enabled."""
    rows = connection.execute(sa.text("PRAGMA compile_options")).fetchall()
    return any(row[0] == "ENABLE_FTS5" for row in rows)


def upgrade() -> None:
    """Create trigram shadow tables, sync triggers, and backfill existing rows.

    On builds without FTS5 the migration still records success while skipping
    every FTS object, so every command stays usable on the LIKE fallback.
    """
    if not _fts5_available(op.get_bind()):
        print(_FTS5_WARNING, file=sys.stderr)
        return
    for fts_table, source_table in _FTS_LAYERS:
        op.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {fts_table} USING fts5("
            "id UNINDEXED, content, tokenize='trigram')"
        )
        op.execute(
            f"INSERT INTO {fts_table}(rowid, id, content) "
            f"SELECT src.rowid, src.id, src.content FROM {source_table} AS src "
            f"WHERE NOT EXISTS ("
            f"SELECT 1 FROM {fts_table} WHERE {fts_table}.rowid = src.rowid)"
        )
        op.execute(
            f"CREATE TRIGGER IF NOT EXISTS {fts_table}_ai "
            f"AFTER INSERT ON {source_table} BEGIN "
            f"INSERT INTO {fts_table}(rowid, id, content) "
            f"VALUES (new.rowid, new.id, new.content); END"
        )
        op.execute(
            f"CREATE TRIGGER IF NOT EXISTS {fts_table}_ad "
            f"AFTER DELETE ON {source_table} BEGIN "
            f"DELETE FROM {fts_table} WHERE rowid = old.rowid; END"
        )
        op.execute(
            f"CREATE TRIGGER IF NOT EXISTS {fts_table}_au "
            f"AFTER UPDATE ON {source_table} BEGIN "
            f"DELETE FROM {fts_table} WHERE rowid = old.rowid; "
            f"INSERT INTO {fts_table}(rowid, id, content) "
            f"VALUES (new.rowid, new.id, new.content); END"
        )


def downgrade() -> None:
    """Drop sync triggers and trigram shadow tables."""
    for fts_table, _source_table in _FTS_LAYERS:
        op.execute(f"DROP TRIGGER IF EXISTS {fts_table}_ai")
        op.execute(f"DROP TRIGGER IF EXISTS {fts_table}_ad")
        op.execute(f"DROP TRIGGER IF EXISTS {fts_table}_au")
        op.execute(f"DROP TABLE IF EXISTS {fts_table}")
