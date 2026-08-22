"""Motive services (N27 S1): deterministic derivation and strength lifecycle.

A motive is one thing a partner carries - not a todo. It has no deadline, no
assignee and no claim/accept semantics; it only biases later behavior.
Decay follows the N17 whole-day laziness semantics (never deletes), and
clear_motive is the only removal path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, AgentMotive, AgentRole, MotiveKind

_MOTIVE_EVENT_SOURCE_PREFIX = "event:"


def _now_utc(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    """Treat naive datetimes (e.g. SQLite CURRENT_TIMESTAMP backfill) as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _effective_strength(
    motive: AgentMotive,
    now: datetime,
    decay_per_day: int,
) -> int:
    """Whole-day decay since last_touched_at, clamped to [0, 100] (N17 style)."""
    days = (_as_utc(now) - _as_utc(motive.last_touched_at)).days
    if days < 0:
        days = 0
    return max(0, min(100, motive.strength - decay_per_day * days))


@dataclass(frozen=True)
class _MotiveRule:
    """One deterministic event-kind -> motive template (N27 S1)."""

    kind: MotiveKind
    content: str
    role: str | None = None


#: Deterministic template rules; ``role`` is the fallback owner when the
#: caller does not pass ``context["agent_id"]`` (first partner of that role
#: by creation order). Contents are static so behavior is assertable under
#: mock and reproducible across runs.
_MOTIVE_RULES: dict[str, _MotiveRule] = {
    "draft_generated": _MotiveRule(
        kind=MotiveKind.GOAL,
        content="新章已交",
        role=AgentRole.WRITER,
    ),
    "refusal": _MotiveRule(
        kind=MotiveKind.PENDING_ISSUE,
        content="被拒了，这事还惦记着",
    ),
    "review_conflict": _MotiveRule(
        kind=MotiveKind.FORESHADOW,
        content="审稿时发现前后矛盾，先记一笔",
        role=AgentRole.REVIEWER,
    ),
}


def derive_motives(
    db: DB,
    workspace_id: str,
    event_kind: str,
    context: dict[str, Any] | None = None,
) -> list[AgentMotive]:
    """Create motives from a business event using deterministic rules.

    ``context`` may carry ``agent_id`` to pick the motive owner explicitly;
    otherwise the rule's fallback role is resolved (first partner of that
    role in the workspace). Unknown event kinds raise USAGE_ERROR so callers
    opt in per event kind instead of silently skipping.
    """
    context = context if context is not None else {}
    rule = _MOTIVE_RULES.get(event_kind)
    if rule is None:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"unknown motive event kind: {event_kind}",
        )
    agent_id = context.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        if rule.role is None:
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                f"context must provide agent_id for event kind: {event_kind}",
            )
        with db.workspace_session(workspace_id) as session:
            fallback = (
                session.query(Agent)
                .filter_by(workspace_id=workspace_id, role=rule.role)
                .order_by(Agent.created_at, Agent.id)
                .first()
            )
        if fallback is None:
            raise NovelError(
                ErrorCode.NOT_FOUND,
                f"no {rule.role} in workspace: {workspace_id}",
            )
        agent_id = fallback.id
    with db.workspace_session(workspace_id) as session:
        if (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, id=agent_id)
            .first()
            is None
        ):
            raise NovelError(ErrorCode.NOT_FOUND, f"agent not found: {agent_id}")
        motive = AgentMotive(
            workspace_id=workspace_id,
            agent_id=agent_id,
            kind=rule.kind,
            content=rule.content,
            source=f"{_MOTIVE_EVENT_SOURCE_PREFIX}{event_kind}",
        )
        session.add(motive)
        session.commit()
    return [motive]


def strengthen_motive(
    db: DB,
    workspace_id: str,
    motive_id: str,
    amount: int,
) -> AgentMotive:
    """Move one motive's strength by ``amount``, clamped to [0, 100]."""
    with db.workspace_session(workspace_id) as session:
        motive = (
            session.query(AgentMotive)
            .filter_by(workspace_id=workspace_id, id=motive_id)
            .first()
        )
        if motive is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"motive not found: {motive_id}")
        motive.strength = max(0, min(100, motive.strength + amount))
        motive.last_touched_at = datetime.now(UTC)
        session.commit()
        return motive


def decay_motives(
    db: DB,
    workspace_id: str,
    now: datetime | None = None,
) -> list[AgentMotive]:
    """Recompute and persist strength for every motive (N17 whole-day style).

    Only motives whose strength actually changes are written and returned, so
    re-running with the same ``now`` is a no-op (idempotent). The elapsed
    interval is consumed by advancing last_touched_at to ``now`` on each
    write. Decay never deletes a motive.
    """
    now = _now_utc(now)
    decay_per_day = load_settings().memory_decay_per_day
    changed: list[AgentMotive] = []
    with db.workspace_session(workspace_id) as session:
        motives = (
            session.query(AgentMotive)
            .filter_by(workspace_id=workspace_id)
            .order_by(AgentMotive.id)
            .all()
        )
        for motive in motives:
            target = _effective_strength(motive, now, decay_per_day)
            if motive.strength != target:
                motive.strength = target
                motive.last_touched_at = now
                changed.append(motive)
        session.commit()
    return changed


def clear_motive(db: DB, workspace_id: str, motive_id: str) -> AgentMotive:
    """Resolve a motive (foreshadow recovered, conflict settled, author let go)."""
    with db.workspace_session(workspace_id) as session:
        motive = (
            session.query(AgentMotive)
            .filter_by(workspace_id=workspace_id, id=motive_id)
            .first()
        )
        if motive is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"motive not found: {motive_id}")
        session.delete(motive)
        session.commit()
        return motive


def list_motives(
    db: DB,
    workspace_id: str,
    agent_id: str | None = None,
) -> list[AgentMotive]:
    """List motives; without agent_id every partner's motives are returned.

    Ordering is strength descending, then created_at ascending, then id
    ascending, so the order is deterministic and unchanged when strengths tie.
    """
    with db.workspace_session(workspace_id) as session:
        query = session.query(AgentMotive).filter_by(workspace_id=workspace_id)
        if agent_id is not None:
            query = query.filter_by(agent_id=agent_id)
        return list(
            query.order_by(
                AgentMotive.strength.desc(),
                AgentMotive.created_at,
                AgentMotive.id,
            ).all()
        )
