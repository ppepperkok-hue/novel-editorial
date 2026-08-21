"""Inspiration material services for workspaces (N15)."""

from __future__ import annotations

import sys

from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.events import EventType
from novel_editorial.store.db import DB
from novel_editorial.store.events import record_event
from novel_editorial.store.models import Inspiration

DEFAULT_INSPIRATION_KIND = "灵感"


def _record_event_safe(
    db: DB,
    workspace_id: str,
    *,
    kind: str,
    inspiration: Inspiration,
) -> None:
    """Persist a SYSTEM event; a failure only warns and never rolls back."""
    try:
        record_event(
            db,
            workspace_id,
            type=EventType.SYSTEM,
            actor="system",
            payload={
                "inspiration_id": inspiration.id,
                "kind": inspiration.kind,
            },
        )
    except Exception as exc:  # noqa: BLE001 - event recording is best-effort
        print(f"warning: {kind} event skipped: {exc}", file=sys.stderr)


def add_inspiration(
    db: DB,
    workspace_id: str,
    *,
    content: str,
    kind: str = DEFAULT_INSPIRATION_KIND,
    source: str = "",
) -> Inspiration:
    """Create one inspiration row and persist an inspiration_created event."""
    if not content.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "inspiration content must not be empty")
    if not kind.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "inspiration kind must not be empty")
    get_workspace_or_raise(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        inspiration = Inspiration(
            workspace_id=workspace_id,
            kind=kind,
            content=content,
            source=source,
        )
        session.add(inspiration)
        session.commit()
    _record_event_safe(
        db,
        workspace_id,
        kind="inspiration_created",
        inspiration=inspiration,
    )
    return inspiration


def list_inspirations(
    db: DB,
    workspace_id: str,
    *,
    kind: str | None = None,
    keyword: str | None = None,
) -> list[Inspiration]:
    """List inspirations newest first (updated_at desc, id asc as tiebreak).

    ``kind`` filters exactly; ``keyword`` matches content/source as a
    case-insensitive substring. Empty result is an empty list.
    """
    get_workspace_or_raise(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        query = session.query(Inspiration).filter_by(workspace_id=workspace_id)
        if kind is not None:
            query = query.filter_by(kind=kind)
        rows = list(query.all())
    if keyword:
        needle = keyword.lower()
        rows = [
            row
            for row in rows
            if needle in row.content.lower() or needle in row.source.lower()
        ]
    rows.sort(key=lambda row: row.id)
    rows.sort(key=lambda row: row.updated_at, reverse=True)
    return rows


def get_inspiration(db: DB, workspace_id: str, inspiration_id: str) -> Inspiration:
    """Fetch one inspiration in a workspace, or raise NOT_FOUND."""
    get_workspace_or_raise(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        inspiration = (
            session.query(Inspiration)
            .filter_by(workspace_id=workspace_id, id=inspiration_id)
            .first()
        )
    if inspiration is None:
        raise NovelError(ErrorCode.NOT_FOUND, f"inspiration not found: {inspiration_id}")
    return inspiration


def remove_inspiration(
    db: DB,
    workspace_id: str,
    inspiration_id: str,
) -> Inspiration:
    """Delete one inspiration, persist an inspiration_removed event, return the row."""
    inspiration = get_inspiration(db, workspace_id, inspiration_id)
    with db.workspace_session(workspace_id) as session:
        row = session.get(Inspiration, inspiration_id)
        if row is None:
            raise NovelError(
                ErrorCode.NOT_FOUND, f"inspiration not found: {inspiration_id}"
            )
        session.delete(row)
        session.commit()
    _record_event_safe(
        db,
        workspace_id,
        kind="inspiration_removed",
        inspiration=inspiration,
    )
    return inspiration
