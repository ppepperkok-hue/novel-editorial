"""Behavior timeline services: append records and query the current state."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from sqlalchemy import literal_column

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import BehaviorTimeline

BEHAVIOR_KINDS = ("impression", "relationship", "viewpoint")

# SQLite assigns every row an implicit rowid. Rows are only appended, never
# deleted, so rowid order equals insertion order even when created_at collides
# within one tick; rowid is the cursor key, matching store/events.py.
_ROWID = literal_column("rowid")


def record_behavior_entry(
    db: DB,
    workspace_id: str,
    *,
    agent_id: str,
    kind: str,
    target: str,
    summary: str = "",
    before_value: str | None = None,
    after_value: str | None = None,
    source: str = "",
) -> BehaviorTimeline:
    """Append one behavior record in its own transaction and return it."""
    if kind not in BEHAVIOR_KINDS:
        expected = ", ".join(BEHAVIOR_KINDS)
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"invalid behavior kind: {kind} (expected one of: {expected})",
        )
    if not agent_id.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "agent_id must not be empty")
    if not target.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "target must not be empty")
    with db.workspace_session(workspace_id) as session:
        entry = BehaviorTimeline(
            workspace_id=workspace_id,
            agent_id=agent_id,
            kind=kind,
            target=target,
            summary=summary,
            before_value=before_value,
            after_value=after_value,
            source=source,
        )
        session.add(entry)
        session.commit()
        return entry


def record_behavior_entry_safe(
    db: DB,
    workspace_id: str,
    *,
    agent_id: str,
    kind: str,
    target: str,
    summary: str = "",
    before_value: str | None = None,
    after_value: str | None = None,
    source: str = "",
) -> bool:
    """Append one behavior record, degrading to a stderr warning on failure.

    Behavior traces are post-hoc sediment: a trace write failure must never
    roll the business result back, so every exception is caught and reported.
    """
    try:
        record_behavior_entry(
            db,
            workspace_id,
            agent_id=agent_id,
            kind=kind,
            target=target,
            summary=summary,
            before_value=before_value,
            after_value=after_value,
            source=source,
        )
    except Exception as exc:
        print(f"warning: behavior trace skipped: {exc}", file=sys.stderr)
        return False
    return True


def list_behavior_timeline(
    db: DB,
    workspace_id: str,
    *,
    agent_id: str | None = None,
    kind: str | Sequence[str] | None = None,
    limit: int = 20,
) -> list[BehaviorTimeline]:
    """Return behavior rows oldest first (insertion order), optionally filtered.

    ``kind`` accepts a single value or a sequence; multiple kinds are matched
    in one query so the insertion-order limit applies across all of them. An
    empty string or an empty sequence is equivalent to no kind filter.
    """
    with db.workspace_session(workspace_id) as session:
        query = session.query(BehaviorTimeline).filter_by(workspace_id=workspace_id)
        if agent_id is not None:
            query = query.filter(BehaviorTimeline.agent_id == agent_id)
        if kind:
            kinds = [kind] if isinstance(kind, str) else list(kind)
            query = query.filter(BehaviorTimeline.kind.in_(kinds))
        return query.order_by(_ROWID.asc()).limit(limit).all()


def current_behavior_state(
    db: DB,
    workspace_id: str,
    *,
    agent_id: str | None = None,
    kind: str | None = None,
) -> dict[tuple[str, str, str], BehaviorTimeline]:
    """Return the latest record per (agent_id, kind, target) group.

    Event-sourcing semantics: the current impression / relationship / viewpoint
    for a group is its newest row, while the full history stays in the timeline.
    """
    with db.workspace_session(workspace_id) as session:
        query = session.query(BehaviorTimeline).filter_by(workspace_id=workspace_id)
        if agent_id is not None:
            query = query.filter(BehaviorTimeline.agent_id == agent_id)
        if kind is not None:
            query = query.filter(BehaviorTimeline.kind == kind)
        rows = query.order_by(_ROWID.asc()).all()
    latest: dict[tuple[str, str, str], BehaviorTimeline] = {}
    for row in rows:
        latest[(row.agent_id, row.kind, row.target)] = row
    return latest
