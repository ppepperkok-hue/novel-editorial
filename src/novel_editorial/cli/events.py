"""Events command group: inspect the workspace event flow."""

from __future__ import annotations

import json
import time

import typer

from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.events import EventType
from novel_editorial.store.db import DB
from novel_editorial.store.events import latest_rowid, list_events, list_events_since
from novel_editorial.store.models import Event

events_app = typer.Typer(help="Inspect the workspace event flow")

EVENT_PAYLOAD_LIMIT = 80


def _resolve_event_types(types: list[str] | None) -> list[EventType] | None:
    if not types:
        return None
    resolved: list[EventType] = []
    for value in types:
        try:
            resolved.append(EventType(value))
        except ValueError as exc:
            raise NovelError(ErrorCode.USAGE_ERROR, f"unknown event type: {value}") from exc
    return resolved


def _render_event(event: Event) -> str:
    try:
        payload = json.loads(event.payload or "{}")
    except json.JSONDecodeError:
        payload = {}
    payload_text = json.dumps(payload, ensure_ascii=False)
    if len(payload_text) > EVENT_PAYLOAD_LIMIT:
        payload_text = payload_text[:EVENT_PAYLOAD_LIMIT] + "..."
    when = event.time.isoformat(timespec="seconds")
    return f"{when} [{event.type}] {event.actor} {payload_text}"


_EVENT_TYPES_OPTION = typer.Option(None, "--type", help="Filter by event type (repeatable)")


@events_app.command("list")
def events_list(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    types: list[str] | None = _EVENT_TYPES_OPTION,
    limit: int = typer.Option(20, "--limit", min=1, help="Max events to show"),
) -> None:
    """List workspace events, newest first."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    events = list_events(db, workspace_id, types=_resolve_event_types(types), limit=limit)
    if not events:
        typer.echo("no events yet")
        return
    for event in events:
        typer.echo(_render_event(event))


@events_app.command("watch")
def events_watch(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    interval: float = typer.Option(2.0, "--interval", min=0.1, help="Poll interval in seconds"),
) -> None:
    """Watch for new workspace events (Ctrl+C to stop)."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    cursor_rowid = latest_rowid(db, workspace_id)
    try:
        while True:
            for record in list_events_since(db, workspace_id, after_rowid=cursor_rowid):
                typer.echo(_render_event(record.event))
                cursor_rowid = record.rowid
            time.sleep(interval)
    except KeyboardInterrupt:
        raise typer.Exit(0) from None
