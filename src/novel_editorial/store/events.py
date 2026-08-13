"""Event persistence: write and query the shared event contract."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from novel_editorial.events import EventType
from novel_editorial.store.db import DB
from novel_editorial.store.models import Event

_LAST_EVENT_TIME: datetime | None = None


def _next_event_time() -> datetime:
    """Return a strictly increasing UTC time so (time, id) ordering is stable."""
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
    """Return events newest first, optionally filtered by type."""
    with db.workspace_session(workspace_id) as session:
        query = session.query(Event).filter_by(workspace_id=workspace_id)
        if types:
            query = query.filter(Event.type.in_([event_type.value for event_type in types]))
        return query.order_by(Event.time.desc(), Event.id.desc()).limit(limit).all()


def list_events_since(
    db: DB,
    workspace_id: str,
    *,
    after_time: datetime | None = None,
    after_id: str | None = None,
) -> list[Event]:
    """Return events strictly after the (time, id) cursor, oldest first."""
    with db.workspace_session(workspace_id) as session:
        query = session.query(Event).filter_by(workspace_id=workspace_id)
        if after_time is not None:
            query = query.filter(
                or_(
                    Event.time > after_time,
                    and_(Event.time == after_time, Event.id > after_id),
                )
            )
        return query.order_by(Event.time.asc(), Event.id.asc()).all()
