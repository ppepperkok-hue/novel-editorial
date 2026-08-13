"""Private memory services for editorial partners (U18)."""

from __future__ import annotations

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, AgentMemory


def add_memory_note(
    db: DB,
    workspace_id: str,
    agent_id: str,
    *,
    content: str,
) -> AgentMemory:
    """Write a private note owned by one partner; it belongs to that partner alone."""
    if not content.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "memory content must not be empty")
    with db.workspace_session(workspace_id) as session:
        agent = session.query(Agent).filter_by(workspace_id=workspace_id, id=agent_id).first()
        if agent is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"agent not found: {agent_id}")
        note = AgentMemory(workspace_id=workspace_id, agent_id=agent_id, content=content)
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
