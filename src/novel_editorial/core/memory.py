"""Private memory services for editorial partners (U18)."""

from __future__ import annotations

from datetime import UTC, datetime

from novel_editorial.core.chat import AUTHOR_ACTOR, ROLE_ALIASES
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, AgentMemory

VALID_ACTORS: tuple[str, ...] = (AUTHOR_ACTOR, *ROLE_ALIASES)

AUTHOR_READ_ONLY = "作者只读，请用 --as <伙伴别名> 以伙伴身份写入"


def _now_utc(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    """Treat naive datetimes (e.g. SQLite CURRENT_TIMESTAMP backfill) as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def effective_strength(note: AgentMemory, now: datetime) -> int:
    """Compute a note's strength after whole days since it was last accessed.

    Pure computation: never writes to the database. Negative day counts are
    clamped to zero and the result is clamped to [0, 100].
    """
    days = (_as_utc(now) - _as_utc(note.last_accessed_at)).days
    if days < 0:
        days = 0
    decay = load_settings().memory_decay_per_day * days
    return max(0, min(100, note.strength - decay))


def add_memory_note(
    db: DB,
    workspace_id: str,
    agent_id: str,
    *,
    actor: str = AUTHOR_ACTOR,
    content: str,
) -> AgentMemory:
    """Write a private note owned by one partner.

    A partner may only write to itself; the author is read-only and may never
    write. The actor is used only for permission checks and is not persisted.
    """
    if actor not in VALID_ACTORS:
        expected = ", ".join(VALID_ACTORS)
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"invalid actor: {actor} (expected one of: {expected})",
        )
    if not content.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "memory content must not be empty")
    if len(content.splitlines()) > 1:
        raise NovelError(ErrorCode.USAGE_ERROR, "memory content must not contain newlines")
    with db.workspace_session(workspace_id) as session:
        agent = session.query(Agent).filter_by(workspace_id=workspace_id, id=agent_id).first()
        if agent is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"agent not found: {agent_id}")
        if actor == AUTHOR_ACTOR:
            raise NovelError(ErrorCode.USAGE_ERROR, AUTHOR_READ_ONLY)
        role = ROLE_ALIASES.get(actor)
        if role is None or agent.role != role:
            raise NovelError(ErrorCode.USAGE_ERROR, f"{actor} may only write own notes")
        note = AgentMemory(
            workspace_id=workspace_id,
            agent_id=agent_id,
            content=content,
        )
        session.add(note)
        session.commit()
        return note


def list_memory_notes(
    db: DB,
    workspace_id: str,
    agent_id: str | None = None,
    include_archived: bool = False,
) -> list[AgentMemory]:
    """List private notes; without agent_id the boss sees every partner's notes.

    Archived notes are excluded unless include_archived=True. Ordering is
    strength descending, then created_at ascending, then id ascending, so the
    order is deterministic and unchanged when every strength is equal.
    """
    with db.workspace_session(workspace_id) as session:
        query = session.query(AgentMemory).filter_by(workspace_id=workspace_id)
        if not include_archived:
            query = query.filter(AgentMemory.archived_at.is_(None))
        if agent_id is not None:
            query = query.filter_by(agent_id=agent_id)
        return list(
            query.order_by(
                AgentMemory.strength.desc(),
                AgentMemory.created_at,
                AgentMemory.id,
            ).all()
        )


def apply_memory_decay(
    db: DB,
    workspace_id: str,
    now: datetime | None = None,
) -> list[AgentMemory]:
    """Recompute and persist strength for active (non-archived) notes.

    Only notes whose strength actually changes are written and returned, so
    re-running with the same `now` is a no-op (idempotent). The elapsed decay
    interval is consumed by advancing last_accessed_at to `now` on each write;
    otherwise the same interval would be re-decayed on the next run.
    """
    now = _now_utc(now)
    changed: list[AgentMemory] = []
    with db.workspace_session(workspace_id) as session:
        notes = (
            session.query(AgentMemory)
            .filter_by(workspace_id=workspace_id)
            .filter(AgentMemory.archived_at.is_(None))
            .order_by(AgentMemory.id)
            .all()
        )
        for note in notes:
            target = effective_strength(note, now)
            if note.strength != target:
                note.strength = target
                note.last_accessed_at = now
                changed.append(note)
        session.commit()
    return changed


def list_archive_candidates(
    db: DB,
    workspace_id: str,
    now: datetime | None = None,
) -> list[AgentMemory]:
    """List active notes whose effective strength is at or below the threshold."""
    now = _now_utc(now)
    threshold = load_settings().memory_archive_threshold
    candidates: list[AgentMemory] = []
    with db.workspace_session(workspace_id) as session:
        notes = (
            session.query(AgentMemory)
            .filter_by(workspace_id=workspace_id)
            .filter(AgentMemory.archived_at.is_(None))
            .order_by(AgentMemory.id)
            .all()
        )
        for note in notes:
            if effective_strength(note, now) <= threshold:
                candidates.append(note)
    return candidates


def rehearse_memory_note(
    db: DB,
    workspace_id: str,
    memory_id: str,
    now: datetime | None = None,
) -> AgentMemory:
    """Boost one note's strength and refresh its last-accessed time."""
    now = _now_utc(now)
    boost = load_settings().memory_rehearsal_boost
    with db.workspace_session(workspace_id) as session:
        note = (
            session.query(AgentMemory)
            .filter_by(workspace_id=workspace_id, id=memory_id)
            .first()
        )
        if note is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"memory note not found: {memory_id}")
        if note.archived_at is not None:
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                f"archived memory note cannot be rehearsed: {memory_id}",
            )
        note.strength = min(100, note.strength + boost)
        note.last_accessed_at = now
        session.commit()
        return note


def archive_memory_notes(
    db: DB,
    workspace_id: str,
    note_ids: list[str] | None = None,
    *,
    candidates: bool = False,
    now: datetime | None = None,
) -> list[AgentMemory]:
    """Archive explicit notes (any strength) or every threshold candidate."""
    now = _now_utc(now)
    if candidates and note_ids:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            "cannot combine explicit note_ids with candidates=True",
        )
    with db.workspace_session(workspace_id) as session:
        if candidates:
            threshold = load_settings().memory_archive_threshold
            active = (
                session.query(AgentMemory)
                .filter_by(workspace_id=workspace_id)
                .filter(AgentMemory.archived_at.is_(None))
                .all()
            )
            targets = [
                note for note in active if effective_strength(note, now) <= threshold
            ]
        else:
            targets = []
            for memory_id in note_ids or []:
                note = (
                    session.query(AgentMemory)
                    .filter_by(workspace_id=workspace_id, id=memory_id)
                    .first()
                )
                if note is None:
                    raise NovelError(
                        ErrorCode.NOT_FOUND,
                        f"memory note not found: {memory_id}",
                    )
                targets.append(note)
        for note in targets:
            note.archived_at = now
        session.commit()
        return targets


def restore_memory_notes(
    db: DB,
    workspace_id: str,
    note_ids: list[str],
    now: datetime | None = None,
) -> list[AgentMemory]:
    """Clear archived_at while keeping strength and last-accessed time as-is."""
    restored: list[AgentMemory] = []
    with db.workspace_session(workspace_id) as session:
        for memory_id in note_ids:
            note = (
                session.query(AgentMemory)
                .filter_by(workspace_id=workspace_id, id=memory_id)
                .first()
            )
            if note is None:
                raise NovelError(
                    ErrorCode.NOT_FOUND,
                    f"memory note not found: {memory_id}",
                )
            note.archived_at = None
            restored.append(note)
        session.commit()
    return restored


def delete_memory_note(db: DB, workspace_id: str, memory_id: str) -> None:
    """Delete one private note by id."""
    with db.workspace_session(workspace_id) as session:
        note = (
            session.query(AgentMemory)
            .filter_by(workspace_id=workspace_id, id=memory_id)
            .first()
        )
        if note is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"memory note not found: {memory_id}")
        session.delete(note)
        session.commit()
