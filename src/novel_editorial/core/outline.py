"""Versioned outline plan services for workspaces (N13 J2).

An outline is an optional, versioned creation plan: each revision appends a
new row with a bumped version, the current outline is the newest row, and the
outline is never a prerequisite for any creation command.
"""

from __future__ import annotations

import sys

from sqlalchemy.orm import Session

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.events import EventType
from novel_editorial.store.db import DB
from novel_editorial.store.events import record_event
from novel_editorial.store.models import Outline, Workspace


def _ensure_workspace(db: DB, workspace_id: str) -> None:
    """Raise NOT_FOUND when the workspace is not registered."""
    with db.global_session() as session:
        if session.get(Workspace, workspace_id) is None:
            raise NovelError(
                ErrorCode.NOT_FOUND, f"workspace not found: {workspace_id}"
            )


def _latest_in_session(
    session: Session, workspace_id: str
) -> Outline | None:
    """Return the newest outline row (highest version), or None."""
    return (
        session.query(Outline)
        .filter_by(workspace_id=workspace_id)
        .order_by(Outline.version.desc())
        .first()
    )


def _record_event_safe(
    db: DB, workspace_id: str, *, kind: str, payload: dict
) -> None:
    """Persist a SYSTEM event; a failure only warns and never rolls back."""
    try:
        record_event(
            db,
            workspace_id,
            type=EventType.SYSTEM,
            actor=payload["actor"],
            payload={"kind": kind, **payload},
        )
    except Exception as exc:  # noqa: BLE001 - event recording is best-effort
        print(f"warning: {kind} event skipped: {exc}", file=sys.stderr)


def create_outline(
    db: DB,
    workspace_id: str,
    *,
    content: str,
    actor: str,
    reason: str = "initial",
) -> Outline:
    """Create the first outline version; an existing outline is a usage error."""
    if not content.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "outline content must not be empty")
    if not actor.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "outline actor must not be empty")
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        if _latest_in_session(session, workspace_id) is not None:
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                "outline already exists; use outline revise",
            )
        outline = Outline(
            workspace_id=workspace_id,
            content=content,
            version=1,
            reason=reason,
            actor=actor,
        )
        session.add(outline)
        session.commit()
        outline_id = outline.id
        version = outline.version
    _record_event_safe(
        db,
        workspace_id,
        kind="outline_created",
        payload={
            "outline_id": outline_id,
            "version": version,
            "actor": actor,
            "reason": reason,
        },
    )
    return outline


def revise_outline(
    db: DB,
    workspace_id: str,
    *,
    content: str,
    reason: str,
    actor: str,
) -> Outline:
    """Revise the current outline: append a new row with version + 1."""
    if not content.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "outline content must not be empty")
    if not reason.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "outline reason must not be empty")
    if not actor.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "outline actor must not be empty")
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        current = _latest_in_session(session, workspace_id)
        if current is None:
            raise NovelError(
                ErrorCode.NOT_FOUND,
                "outline not found; create one before revising",
            )
        outline = Outline(
            workspace_id=workspace_id,
            content=content,
            version=current.version + 1,
            reason=reason,
            actor=actor,
        )
        session.add(outline)
        session.commit()
        outline_id = outline.id
        version = outline.version
    _record_event_safe(
        db,
        workspace_id,
        kind="outline_revised",
        payload={
            "outline_id": outline_id,
            "version": version,
            "actor": actor,
            "reason": reason,
        },
    )
    return outline


def get_outline(db: DB, workspace_id: str) -> Outline | None:
    """Return the current (highest-version) outline row, or None."""
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        return _latest_in_session(session, workspace_id)


def list_outline_versions(
    db: DB, workspace_id: str, limit: int = 20
) -> list[Outline]:
    """Return outline versions newest first, capped at limit."""
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        return list(
            session.query(Outline)
            .filter_by(workspace_id=workspace_id)
            .order_by(Outline.version.desc())
            .limit(limit)
            .all()
        )
