"""Agent profile services."""

from __future__ import annotations

from novel_editorial.core.chat import ROLE_ALIASES, get_agent
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent

EDITABLE_FIELDS: tuple[str, ...] = (
    "personality",
    "stance",
    "values",
    "aesthetic",
    "emotion_baseline",
    "work_habits",
    "weaknesses",
    "relationship_presets",
    "private_motive",
)


def resolve_agent(db: DB, workspace_id: str, target: str) -> Agent:
    """Resolve an agent by role alias (e.g. 写手) or by id."""
    role = ROLE_ALIASES.get(target)
    if role is not None:
        return get_agent(db, workspace_id, role)
    with db.workspace_session(workspace_id) as session:
        agent = session.query(Agent).filter_by(workspace_id=workspace_id, id=target).first()
    if agent is None:
        raise NovelError(ErrorCode.NOT_FOUND, f"agent not found: {target}")
    return agent


def update_agent_field(
    db: DB,
    workspace_id: str,
    agent_id: str,
    *,
    field: str,
    value: str,
) -> Agent:
    if field not in EDITABLE_FIELDS:
        raise NovelError(ErrorCode.USAGE_ERROR, f"unknown profile field: {field}")
    with db.workspace_session(workspace_id) as session:
        agent = session.query(Agent).filter_by(workspace_id=workspace_id, id=agent_id).first()
        if agent is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"agent not found: {agent_id}")
        setattr(agent, field, value)
        session.commit()
        return agent
