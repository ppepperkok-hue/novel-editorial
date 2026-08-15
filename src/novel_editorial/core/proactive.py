"""Proactive behavior model: kinds, payloads, trigger registry, and rate limiting.

A1 scope only: this module establishes the framework without wiring any concrete
role situation (that lands in A2). The existing first-round PROACTIVE_QUESTION
flow in chat/talk is deliberately left untouched.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import Message

#: Proactive behavior kinds; the values double as the payload "kind" field.
PROACTIVE_KIND_QUESTION = "proactive_question"
PROACTIVE_KIND_REVIEW = "proactive_review"
PROACTIVE_KIND_CONSISTENCY = "proactive_consistency"
PROACTIVE_KIND_DIRECTION = "proactive_direction"
PROACTIVE_KIND_REPORT = "proactive_report"

PROACTIVE_KINDS: frozenset[str] = frozenset(
    {
        PROACTIVE_KIND_QUESTION,
        PROACTIVE_KIND_REVIEW,
        PROACTIVE_KIND_CONSISTENCY,
        PROACTIVE_KIND_DIRECTION,
        PROACTIVE_KIND_REPORT,
    }
)

INITIATOR_AGENT = "agent"

TriggerContext = Mapping[str, Any]
ConditionFn = Callable[[TriggerContext], bool]


@dataclass(frozen=True)
class ProactiveSpec:
    """One registered situation: condition, emitting partner, and fixed copy."""

    trigger: str
    agent: str
    kind: str
    content: str
    condition: ConditionFn


@dataclass(frozen=True)
class ProactiveCandidate:
    """A candidate proactive message: (agent, kind, content)."""

    agent: str
    kind: str
    content: str


_PROACTIVE_TRIGGERS: dict[str, list[ProactiveSpec]] = {}


def register_proactive_trigger(
    *,
    trigger: str,
    agent: str,
    kind: str,
    content: str,
    condition: ConditionFn,
) -> ProactiveSpec:
    """Register one (situation, condition) pair for later evaluation."""
    if not trigger or not agent or not content:
        raise NovelError(
            ErrorCode.USAGE_ERROR, "trigger, agent and content must not be empty"
        )
    if kind not in PROACTIVE_KINDS:
        raise NovelError(ErrorCode.USAGE_ERROR, f"unknown proactive kind: {kind}")
    spec = ProactiveSpec(
        trigger=trigger,
        agent=agent,
        kind=kind,
        content=content,
        condition=condition,
    )
    _PROACTIVE_TRIGGERS.setdefault(trigger, []).append(spec)
    return spec


def build_proactive_payload(kind: str, trigger: str) -> dict[str, str]:
    """Build the standard payload carried by a proactive message."""
    if kind not in PROACTIVE_KINDS:
        raise NovelError(ErrorCode.USAGE_ERROR, f"unknown proactive kind: {kind}")
    if not trigger:
        raise NovelError(ErrorCode.USAGE_ERROR, "trigger must not be empty")
    return {"initiator": INITIATOR_AGENT, "kind": kind, "trigger": trigger}


def count_proactive_messages(db: DB, workspace_id: str, agent: str) -> int:
    """Count proactive messages already sent by one partner in one workspace.

    The whitelist filter runs in SQL and returns a COUNT, so message rows (and
    their content) are never materialized in Python. Only payloads carrying the
    agent initiator marker and one of the five proactive kinds are counted.
    """
    with db.workspace_session(workspace_id) as session:
        count_statement = (
            select(func.count())
            .select_from(Message)
            .where(
                Message.workspace_id == workspace_id,
                Message.actor == agent,
                Message.payload.like(f'%"initiator": "{INITIATOR_AGENT}"%'),
                or_(
                    *(
                        Message.payload.like(f'%"kind": "{kind}"%')
                        for kind in sorted(PROACTIVE_KINDS)
                    ),
                ),
            )
        )
        return int(session.scalar(count_statement) or 0)


def proactive_within_limit(db: DB, workspace_id: str, agent: str, max_per_agent: int) -> bool:
    """Return True while one partner still has proactive-message budget left."""
    return count_proactive_messages(db, workspace_id, agent) < max_per_agent


def evaluate_proactive_triggers(
    db: DB,
    workspace_id: str,
    trigger: str,
    context: TriggerContext | None = None,
) -> list[ProactiveCandidate]:
    """Evaluate one situation and return the candidates that should fire.

    A disabled switch returns no candidates, and partners over their
    per-workspace budget are skipped. No messages are written here.
    """
    if not db.settings.proactive_enabled:
        return []
    context = context if context is not None else {}
    candidates: list[ProactiveCandidate] = []
    remaining_budget: dict[str, int] = {}
    for spec in _PROACTIVE_TRIGGERS.get(trigger, []):
        if not spec.condition(context):
            continue
        if spec.agent not in remaining_budget:
            remaining_budget[spec.agent] = (
                db.settings.proactive_max_per_agent
                - count_proactive_messages(db, workspace_id, spec.agent)
            )
        if remaining_budget[spec.agent] <= 0:
            continue
        candidates.append(
            ProactiveCandidate(agent=spec.agent, kind=spec.kind, content=spec.content)
        )
        remaining_budget[spec.agent] -= 1
    return candidates
