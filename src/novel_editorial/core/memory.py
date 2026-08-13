"""Private memory services for editorial partners (U18)."""

from __future__ import annotations

from novel_editorial.core.chat import AUTHOR_ACTOR, ROLE_ALIASES
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, AgentMemory

VALID_ACTORS: tuple[str, ...] = (AUTHOR_ACTOR, *ROLE_ALIASES)

AUTHOR_READ_ONLY = "作者只读，请用 --as <伙伴别名> 以伙伴身份写入"


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
    if "\n" in content or "\r" in content:
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
) -> list[AgentMemory]:
    """List private notes; without agent_id the boss sees every partner's notes."""
    with db.workspace_session(workspace_id) as session:
        query = session.query(AgentMemory).filter_by(workspace_id=workspace_id)
        if agent_id is not None:
            query = query.filter_by(agent_id=agent_id)
        return list(query.order_by(AgentMemory.created_at).all())


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
