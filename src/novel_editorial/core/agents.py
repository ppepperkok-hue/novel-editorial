"""Agent profile services."""

from __future__ import annotations

from sqlalchemy import func

from novel_editorial.core.chat import ROLE_ALIASES, get_agent
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB, DEFAULT_BAND
from novel_editorial.store.models import Agent, AgentRole

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

AGENT_ROLES: frozenset[str] = frozenset(
    {
        AgentRole.EDITOR_IN_CHIEF,
        AgentRole.EDITOR,
        AgentRole.WRITER,
        AgentRole.REVIEWER,
    }
)


def _role_defaults(role: str) -> dict[str, str]:
    for member in DEFAULT_BAND:
        if member["role"] == role:
            return member
    return {}


def create_agent(
    db: DB,
    workspace_id: str,
    *,
    name: str,
    role: str,
    personality: str = "",
) -> Agent:
    """Add one partner to a workspace's editorial band.

    Writers may have multiple instances; every other role stays unique per
    workspace. Names are unique within a workspace, compared case-insensitively.
    Profile fields fall back to the role's DEFAULT_BAND profile.
    """
    cleaned_name = name.strip() if isinstance(name, str) else ""
    if not cleaned_name:
        raise NovelError(ErrorCode.USAGE_ERROR, "agent name must not be empty")
    if role not in AGENT_ROLES:
        raise NovelError(ErrorCode.USAGE_ERROR, f"unknown agent role: {role}")
    defaults = _role_defaults(role)
    cleaned_personality = personality.strip() if isinstance(personality, str) else ""
    with db.workspace_session(workspace_id) as session:
        existing = (
            session.query(Agent)
            .filter(
                Agent.workspace_id == workspace_id,
                func.lower(Agent.name) == cleaned_name.lower(),
            )
            .first()
        )
        if existing is not None:
            raise NovelError(
                ErrorCode.USAGE_ERROR, f"agent already exists: {cleaned_name}"
            )
        if role != AgentRole.WRITER:
            same_role = (
                session.query(Agent)
                .filter_by(workspace_id=workspace_id, role=role)
                .first()
            )
            if same_role is not None:
                raise NovelError(
                    ErrorCode.USAGE_ERROR,
                    f"workspace already has a {role}: {same_role.name}",
                )
        agent = Agent(
            workspace_id=workspace_id,
            name=cleaned_name,
            role=role,
            personality=cleaned_personality or defaults["personality"],
            stance=defaults["stance"],
            values=defaults["values"],
            aesthetic=defaults["aesthetic"],
            emotion_baseline=defaults["emotion_baseline"],
            mood=defaults["mood"],
            work_habits=defaults["work_habits"],
            weaknesses=defaults["weaknesses"],
            relationship_presets=defaults["relationship_presets"],
            private_motive=defaults["private_motive"],
        )
        session.add(agent)
        session.commit()
        return agent


def get_default_writer(db: DB, workspace_id: str) -> Agent:
    """Return the workspace's default writer: the first one by created_at."""
    with db.workspace_session(workspace_id) as session:
        writer = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, role=AgentRole.WRITER)
            .order_by(Agent.created_at.asc(), Agent.id.asc())
            .first()
        )
    if writer is None:
        raise NovelError(ErrorCode.NOT_FOUND, f"no writer in workspace: {workspace_id}")
    return writer


def get_agent_by_id(db: DB, workspace_id: str, agent_id: str) -> Agent | None:
    """Return one agent by id, or None when it does not exist."""
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, id=agent_id)
            .first()
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
