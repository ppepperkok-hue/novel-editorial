"""Proactive behavior model and business-event wiring.

A1 established the five kinds, the trigger registry, SQL-backed frequency
counting, and the enabled/max-per-agent settings. A2 adds the write path used
after real business events: candidates returned by evaluate_proactive_triggers
are persisted as agent messages with the standard payload plus their
agent.message events, reusing the session-scoped message helper from chat.

The writer, editor, reviewer, and editor-in-chief situations are registered
here with fixed, deterministic copy. The existing first-round
PROACTIVE_QUESTION flow in chat/talk is deliberately left untouched.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from string import Template
from typing import Any

from sqlalchemy import func, or_, select

from novel_editorial.core.chat import _record_message_in_session
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

TRIGGER_DRAFT_GENERATED = "draft_generated"
TRIGGER_DRAFT_REVISED = "draft_revised"
TRIGGER_DRAFT_GATE_PASSED = "draft_gate_passed"
TRIGGER_STYLE_SET = "style_set"
TRIGGER_PLOT_PLANTED = "plot_planted"
TRIGGER_TALK_FIRST_ROUND = "talk_first_round"

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


class _RenderContext(dict):
    """Template context that renders missing placeholders as empty strings."""

    def __missing__(self, key: str) -> str:
        return ""


def _render_content(content: str, context: TriggerContext) -> str:
    return Template(content).substitute(_RenderContext(context))


def record_proactive_messages(
    db: DB,
    workspace_id: str,
    trigger: str,
    context: TriggerContext | None = None,
) -> list[Message]:
    """Evaluate one situation and persist the firing candidates.

    Each candidate becomes an agent message carrying the standard proactive
    payload plus its agent.message event. Writes run in their own transaction
    after the business operation already committed, so a proactive failure can
    never roll the business result back; callers decide how to surface it.
    """
    candidates = evaluate_proactive_triggers(db, workspace_id, trigger, context)
    if not candidates:
        return []
    render_context = context if context is not None else {}
    with db.workspace_session(workspace_id) as session:
        messages = [
            _record_message_in_session(
                session,
                workspace_id,
                role="agent",
                actor=candidate.agent,
                content=_render_content(candidate.content, render_context),
                payload=build_proactive_payload(candidate.kind, trigger),
            )
            for candidate in candidates
        ]
        session.commit()
        return messages


def _register_draft_proactive_behaviors() -> None:
    """Register the writer/editor draft situations with fixed, assertable copy."""
    register_proactive_trigger(
        trigger=TRIGGER_DRAFT_GENERATED,
        agent="写手",
        kind=PROACTIVE_KIND_REPORT,
        content="《$title》初稿写完了，我按节奏收尾，先交给你过目。",
        condition=lambda context: context.get("current_version") == 1,
    )
    register_proactive_trigger(
        trigger=TRIGGER_DRAFT_REVISED,
        agent="写手",
        kind=PROACTIVE_KIND_QUESTION,
        content="这章我留了个钩子，下章要不要收？",
        condition=lambda context: context.get("passed") is True
        and not context.get("rebutted", False),
    )
    register_proactive_trigger(
        trigger=TRIGGER_DRAFT_GATE_PASSED,
        agent="责编",
        kind=PROACTIVE_KIND_REVIEW,
        content="《$title》过了质量门，我试读了开头「$excerpt」，节奏在线，建议作者拍板。",
        condition=lambda context: context.get("passed") is True
        and context.get("current_version") == 1,
    )


def _register_reviewer_and_editor_proactive_behaviors() -> None:
    """Register the reviewer (style/plot) and editor-in-chief (talk) situations."""
    register_proactive_trigger(
        trigger=TRIGGER_STYLE_SET,
        agent="审稿",
        kind=PROACTIVE_KIND_CONSISTENCY,
        content=(
            "风格锚点定了：「$description」。"
            "我盯着设定看了一遍，开头那句跟「$description」会不会打架？"
        ),
        condition=lambda context: bool(context.get("description")),
    )
    register_proactive_trigger(
        trigger=TRIGGER_PLOT_PLANTED,
        agent="审稿",
        kind=PROACTIVE_KIND_CONSISTENCY,
        content="线索「$content」埋下了。我记进时间线，回头逐章对照，别让它断在半路。",
        condition=lambda context: True,
    )
    register_proactive_trigger(
        trigger=TRIGGER_TALK_FIRST_ROUND,
        agent="总编",
        kind=PROACTIVE_KIND_DIRECTION,
        content="这部作品的方向还没定：整体基调、核心冲突，咱们先把这些捋清楚再动笔。",
        condition=lambda context: context.get("first_round") is True
        and not context.get("has_style_anchor", False),
    )


_register_draft_proactive_behaviors()
_register_reviewer_and_editor_proactive_behaviors()
