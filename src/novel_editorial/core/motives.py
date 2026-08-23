"""Motive services (N27 S1): deterministic derivation and strength lifecycle.

A motive is one thing a partner carries - not a todo. It has no deadline, no
assignee and no claim/accept semantics; it only biases later behavior.
Decay follows the N17 whole-day laziness semantics (never deletes), and
clear_motive is the only removal path.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.llm.client import LLMClient, LLMMessage
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, AgentMotive, AgentRole, MotiveKind

_MOTIVE_EVENT_SOURCE_PREFIX = "event:"

#: N28-A feedback write-back: the first feedback for a (kind, source) creates
#: the motive at the model's default strength; every later feedback for the
#: same source strengthens it by this delta (clamped to [0, 100] by the shared
#: strength helper). The delta is fixed so repeated feedback stays assertable
#: and reproducible (09 design: deterministic rules, no LLM in the loop).
FEEDBACK_MOTIVE_BOOST = 10


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


def _apply_strength_delta(motive: AgentMotive, amount: int, now: datetime) -> None:
    """Shared strengthen semantics: delta clamped to [0, 100], touch refreshed."""
    motive.strength = max(0, min(100, motive.strength + amount))
    motive.last_touched_at = now


def _warn_feedback_skipped(operation: str, exc: Exception) -> None:
    """Report one skipped feedback write-back on stderr (N28 red line)."""
    print(f"warning: motive feedback skipped ({operation}): {exc}", file=sys.stderr)


def _build_motive_prompt(
    event_kind: str,
    rule: _MotiveRule,
    agent: Agent,
) -> list[LLMMessage]:
    """Build the refinement prompt carrying the event and partner context.

    The prompt names the triggering event, the partner (name + role), the
    motive kind and the deterministic template content, so the LLM rewrites
    the same fact with fuller context and the mock path can assert exactly
    which context was handed over (N28-F: prompt is assertable under mock).
    """
    return [
        LLMMessage(
            role="system",
            content=(
                "你是小说编辑部的设定助手。请把伙伴的一条动机写成一句自然、"
                "简短、口语化的中文内心话，保持原意，不解释、不加引号。"
            ),
        ),
        LLMMessage(
            role="user",
            content=(
                f"事件：{event_kind}\n"
                f"伙伴：{agent.name}（{agent.role}）\n"
                f"动机类型：{rule.kind.value}\n"
                f"模板内容：{rule.content}\n"
                "请改写这条动机内容。"
            ),
        ),
    ]


def _refine_motive_content(
    db: DB,
    event_kind: str,
    rule: _MotiveRule,
    agent: Agent,
    client: LLMClient | None,
) -> str:
    """Return the motive content, LLM-refined when the switch and client are on.

    The deterministic template stays the zero-token path: switch off or no
    client never touches the LLM. With the switch on and a client present the
    refinement runs once per new motive row; any failure - an exception or an
    empty reply - degrades back to the template with an explicit stderr
    warning, because a motive is a post-hoc behavioral fact and must never
    interrupt the business result (N28 red line).
    """
    if client is None or not db.settings.motive_llm_enabled:
        return rule.content
    try:
        result = client.complete(_build_motive_prompt(event_kind, rule, agent))
    except Exception as exc:
        print(
            f"warning: motive LLM refinement failed, falling back to template: {exc}",
            file=sys.stderr,
        )
        return rule.content
    content = result.content.strip()
    if not content:
        print(
            "warning: motive LLM refinement returned empty content, "
            "falling back to template",
            file=sys.stderr,
        )
        return rule.content
    return content


def _strengthen_motive_row(
    session: Session,
    workspace_id: str,
    agent_id: str,
    kind: MotiveKind,
    source: str,
) -> AgentMotive | None:
    """Strengthen the committed motive row matching the unique key, if any.

    Shared by the re-trigger path and the IntegrityError fallback: the row
    may have been committed by a concurrent winner between two sessions, or
    the unique insert may have lost the race; either way the winner is
    strengthened instead of duplicated (S1/S2 one-source-one-line semantics).
    """
    existing = (
        session.query(AgentMotive)
        .filter_by(
            workspace_id=workspace_id,
            agent_id=agent_id,
            kind=kind,
            source=source,
        )
        .order_by(AgentMotive.id)
        .first()
    )
    if existing is None:
        return None
    _apply_strength_delta(
        existing,
        load_settings().memory_rehearsal_boost,
        datetime.now(UTC),
    )
    session.commit()
    return existing


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
    *,
    client: LLMClient | None = None,
) -> list[AgentMotive]:
    """Create motives from a business event using deterministic rules.

    ``context`` may carry ``agent_id`` to pick the motive owner explicitly;
    otherwise the rule's fallback role is resolved (first partner of that
    role in the workspace). Unknown event kinds raise USAGE_ERROR so callers
    opt in per event kind instead of silently skipping. Re-triggering the same
    event for the same (agent, kind, source) never adds a row: the existing
    motive is strengthened by ``memory_rehearsal_boost`` (clamped to 100) and
    its last_touched_at is refreshed, keeping "one motive is one thing".
    The (workspace_id, agent_id, kind, source) uniqueness is enforced by the
    database; if a concurrent winner commits the same source between the
    lookup and the insert, the insert is rejected and this function rolls
    back, re-reads the committed row and strengthens it instead of raising.

    ``client`` is the optional N28-F LLM refinement: with
    ``db.settings.motive_llm_enabled`` on and a client supplied, a brand-new
    motive row gets its content from the client (the prompt carries the event
    and partner context); a failed or empty reply falls back to the template
    with a stderr warning. Switch off, no client, or a re-triggered existing
    motive (which only strengthens) keep the deterministic template - the
    zero-token path. The refinement is deliberately run outside any workspace
    transaction (P2): a short read session resolves the partner and checks
    whether the motive already exists, the session is closed before
    ``client.complete`` runs, and a fresh write session then re-checks and
    inserts, so no SQLite lock is held during the network call.
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
    # Short read session: resolve the partner and check whether the motive
    # already exists, then close the session BEFORE any network call so no
    # SQLite lock is held while client.complete runs (P2).
    with db.workspace_session(workspace_id) as session:
        agent = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, id=agent_id)
            .first()
        )
        if agent is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"agent not found: {agent_id}")
        source = f"{_MOTIVE_EVENT_SOURCE_PREFIX}{event_kind}"
        existing = (
            session.query(AgentMotive)
            .filter_by(
                workspace_id=workspace_id,
                agent_id=agent_id,
                kind=rule.kind,
                source=source,
            )
            .order_by(AgentMotive.id)
            .first()
        )
    if existing is not None:
        # A fresh short session strengthens the existing row; if a concurrent
        # clear removed it in between, fall through and create a new one.
        with db.workspace_session(workspace_id) as session:
            strengthened = _strengthen_motive_row(
                session, workspace_id, agent_id, rule.kind, source
            )
        if strengthened is not None:
            return [strengthened]
    content = _refine_motive_content(db, event_kind, rule, agent, client)
    with db.workspace_session(workspace_id) as session:
        # Re-check inside the write session: a concurrent winner may have
        # committed the same source since the read session closed.
        strengthened = _strengthen_motive_row(
            session, workspace_id, agent_id, rule.kind, source
        )
        if strengthened is not None:
            return [strengthened]
        motive = AgentMotive(
            workspace_id=workspace_id,
            agent_id=agent_id,
            kind=rule.kind,
            content=content,
            source=source,
        )
        session.add(motive)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            strengthened = _strengthen_motive_row(
                session, workspace_id, agent_id, rule.kind, source
            )
            if strengthened is None:
                raise
            return [strengthened]
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
        _apply_strength_delta(motive, amount, datetime.now(UTC))
        session.commit()
    return motive


def upsert_motive_feedback(
    db: DB,
    workspace_id: str,
    agent_id: str,
    *,
    kind: str,
    content: str,
    source: str,
) -> AgentMotive:
    """Create one feedback motive on first write-back, strengthen it on repeat.

    N28-A mirrors derive_motives' "one source one line" invariant: the same
    (workspace_id, agent_id, kind, source) may never insert twice, so the
    first feedback creates the motive at default strength and every later
    feedback for the same source strengthens it by ``FEEDBACK_MOTIVE_BOOST``
    (clamped to 100) and refreshes last_touched_at. The source is supplied by
    the caller so every feedback row stays explainable (``decision:reject``,
    ``author_feedback:praise``, ...).
    """
    with db.workspace_session(workspace_id) as session:
        existing = (
            session.query(AgentMotive)
            .filter_by(
                workspace_id=workspace_id,
                agent_id=agent_id,
                kind=kind,
                source=source,
            )
            .order_by(AgentMotive.id)
            .first()
        )
        if existing is not None:
            _apply_strength_delta(existing, FEEDBACK_MOTIVE_BOOST, datetime.now(UTC))
            session.commit()
            return existing
        motive = AgentMotive(
            workspace_id=workspace_id,
            agent_id=agent_id,
            kind=kind,
            content=content,
            source=source,
        )
        session.add(motive)
        try:
            session.commit()
        except IntegrityError:
            # A concurrent winner committed the same source between the lookup
            # and the insert; roll back and strengthen the winner instead.
            session.rollback()
            existing = (
                session.query(AgentMotive)
                .filter_by(
                    workspace_id=workspace_id,
                    agent_id=agent_id,
                    kind=kind,
                    source=source,
                )
                .order_by(AgentMotive.id)
                .first()
            )
            if existing is None:
                raise
            _apply_strength_delta(existing, FEEDBACK_MOTIVE_BOOST, datetime.now(UTC))
            session.commit()
            return existing
    return motive


def upsert_motive_feedback_safe(
    db: DB,
    workspace_id: str,
    agent_id: str,
    *,
    kind: str,
    content: str,
    source: str,
) -> AgentMotive | None:
    """Upsert one feedback motive, degrading to a stderr warning on failure.

    Feedback write-backs are post-hoc (N28-A/B): a failure must never roll the
    business result back, so every exception is caught and reported. Returns
    the motive on success and None when the write was skipped.
    """
    try:
        return upsert_motive_feedback(
            db,
            workspace_id,
            agent_id,
            kind=kind,
            content=content,
            source=source,
        )
    except Exception as exc:
        _warn_feedback_skipped(f"upsert {source}", exc)
        return None


def clear_motives(
    db: DB,
    workspace_id: str,
    *,
    agent_id: str | None = None,
    kind: str | None = None,
    source: str | None = None,
    source_prefix: str | None = None,
) -> list[AgentMotive]:
    """Delete every matching motive and return the removed rows.

    Filters are optional and AND together. This is the bulk sibling of
    ``clear_motive`` and the N28 write-back resolution path: decide accept
    resolves the writer's draft goal, delegation accept resolves the
    delegator's pending issue, and author let-go phrases resolve the
    workspace's author-related pending issues. Deletion is the designed
    "resolved" lifecycle step; decay never deletes, only clear paths do.
    ``source_prefix`` is an exact string prefix, not a LIKE pattern: ``%``
    and ``_`` in the prefix are escaped so ``event:draft_`` only matches
    sources literally starting with ``event:draft_`` (never ``event:draftX``).
    """
    with db.workspace_session(workspace_id) as session:
        query = session.query(AgentMotive).filter_by(workspace_id=workspace_id)
        if agent_id is not None:
            query = query.filter_by(agent_id=agent_id)
        if kind is not None:
            query = query.filter_by(kind=kind)
        if source is not None:
            query = query.filter_by(source=source)
        if source_prefix is not None:
            escaped_prefix = (
                source_prefix.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            query = query.filter(
                AgentMotive.source.like(f"{escaped_prefix}%", escape="\\")
            )
        rows = query.order_by(AgentMotive.id).all()
        for row in rows:
            session.delete(row)
        session.commit()
        return rows


def clear_motives_safe(
    db: DB,
    workspace_id: str,
    *,
    agent_id: str | None = None,
    kind: str | None = None,
    source: str | None = None,
    source_prefix: str | None = None,
) -> list[AgentMotive]:
    """Clear matching motives, degrading to a stderr warning on failure.

    Same degradation contract as ``upsert_motive_feedback_safe``: the business
    result must survive a failed clear, so the exception is caught, reported,
    and an empty list is returned.
    """
    try:
        return clear_motives(
            db,
            workspace_id,
            agent_id=agent_id,
            kind=kind,
            source=source,
            source_prefix=source_prefix,
        )
    except Exception as exc:
        _warn_feedback_skipped("clear", exc)
        return []


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
