"""Event persistence: write and query the shared event contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import literal_column
from sqlalchemy.orm import Session

from novel_editorial.events import EventType
from novel_editorial.store.db import DB
from novel_editorial.store.models import Event

_LAST_EVENT_TIME: datetime | None = None

# SQLite assigns every events row an implicit rowid. Rows are only inserted,
# never deleted, so rowid order equals cross-process insertion order. The
# (time, id) pair is not monotonic across processes and can silently skip
# same-timestamp events, so the rowid is the cursor key; time is display-only.
_ROWID = literal_column("rowid")


@dataclass(frozen=True)
class EventRecord:
    """One event paired with its insertion-order cursor key."""

    rowid: int
    event: Event


def _next_event_time() -> datetime:
    """Return a strictly increasing UTC time for display; ordering uses rowid."""
    global _LAST_EVENT_TIME
    now = datetime.now(UTC)
    if _LAST_EVENT_TIME is not None and now <= _LAST_EVENT_TIME:
        now = _LAST_EVENT_TIME + timedelta(microseconds=1)
    _LAST_EVENT_TIME = now
    return now


def _type_value(event_type: EventType | str) -> str:
    return event_type.value if isinstance(event_type, EventType) else event_type


def record_event_in_session(
    session: Session,
    workspace_id: str,
    *,
    type: EventType | str,
    actor: str,
    payload: dict[str, Any] | None = None,
) -> Event:
    """Add one event inside an open session; the caller owns the commit."""
    event = Event(
        workspace_id=workspace_id,
        type=_type_value(type),
        time=_next_event_time(),
        actor=actor,
        payload=json.dumps(payload or {}, ensure_ascii=False),
    )
    session.add(event)
    return event


def record_event(
    db: DB,
    workspace_id: str,
    *,
    type: EventType | str,
    actor: str,
    payload: dict[str, Any] | None = None,
) -> Event:
    """Persist one event in its own transaction."""
    with db.workspace_session(workspace_id) as session:
        event = record_event_in_session(
            session,
            workspace_id,
            type=type,
            actor=actor,
            payload=payload,
        )
        session.commit()
        return event


def list_events(
    db: DB,
    workspace_id: str,
    *,
    types: list[EventType] | None = None,
    limit: int = 20,
) -> list[Event]:
    """Return events newest first (insertion order), optionally filtered by type."""
    with db.workspace_session(workspace_id) as session:
        query = session.query(Event).filter_by(workspace_id=workspace_id)
        if types:
            query = query.filter(Event.type.in_([event_type.value for event_type in types]))
        return query.order_by(_ROWID.desc()).limit(limit).all()


def latest_rowid(db: DB, workspace_id: str) -> int | None:
    """Return the cursor key of the most recently inserted event, if any."""
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(_ROWID)
            .select_from(Event)
            .filter(Event.workspace_id == workspace_id)
            .order_by(_ROWID.desc())
            .limit(1)
            .scalar()
        )


def list_events_since(
    db: DB,
    workspace_id: str,
    *,
    after_rowid: int | None = None,
) -> list[EventRecord]:
    """Return events inserted strictly after the rowid cursor, oldest first."""
    with db.workspace_session(workspace_id) as session:
        query = session.query(Event, _ROWID).filter(Event.workspace_id == workspace_id)
        if after_rowid is not None:
            query = query.filter(_ROWID > after_rowid)
        rows = query.order_by(_ROWID.asc()).all()
    return [EventRecord(rowid=rowid, event=event) for event, rowid in rows]
