"""Proactive behavior model and business-event wiring.

A1 established the five kinds, the trigger registry, SQL-backed frequency
counting, and the enabled/max-per-agent settings. A2 adds the write path used
after real business events: candidates returned by evaluate_proactive_triggers
are persisted as agent messages with the standard payload plus their
agent.message events, reusing the session-scoped message helper from chat.

S4 (N27-E/F) moves the evaluation path onto the free-will pipeline from
core/choice.py. After a wired business event fires, the trigger first
sediments a motive when a deterministic rule exists in core/motives.py (no
rule means no motive is ever fabricated); then the registered N1 behaviors -
now single ChoiceCandidate templates - are scored by evaluate_choice using
the work's motives, the partners' four personality params and the
behavior_timeline feedback counts, with freedom_dial / freedom_seed read from
Settings. dial=0 with no motive/feedback interference picks the same single
candidate as the old deterministic path, so the five registered behaviors
keep their exact copy, payload and event contract. Triggers without a topic
entry in core/choice.py keep the legacy deterministic path (condition +
budget), so custom registrations and old call sites behave exactly as before.
The motive_llm_enabled switch only prints a one-time N28 placeholder warning
and never changes behavior.

The writer, editor, reviewer, and editor-in-chief situations are registered
here with fixed, deterministic copy. The existing first-round
PROACTIVE_QUESTION flow in chat/talk is deliberately left untouched.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from string import Template
from typing import Any

from sqlalchemy import func, or_, select

from novel_editorial.core import choice
from novel_editorial.core.agents import list_agents
from novel_editorial.core.chat import _record_message_in_session
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.motives import derive_motives, list_motives
from novel_editorial.store.db import DB
from novel_editorial.store.models import AgentMotive, Message

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

#: Explicit N28 placeholder warning. The switch is a stub: when enabled it is
#: surfaced once instead of being silently ignored, then evaluation continues
#: on the deterministic templates (09 design: LLM refinement is N28's job).
MOTIVE_LLM_WARNING = "LLM motive refinement is not implemented yet (N28)"
_motive_llm_warning_shown = False

#: Trigger -> derive_motives event kind (S4). Sedimentation is opt-in per
#: trigger: only event kinds with an existing deterministic rule in
#: core/motives.py may create a motive, so a trigger without a rule never
#: fabricates one (N27 red line). Today draft_generated is the only S4
#: business-event trigger with a rule; refusal / review_conflict exist in
#: motives.py but are not proactive triggers, so they are deliberately not
#: listed here. Re-triggering the same event never grows the table (S1/S2
#: unique constraint + strengthen-on-repeat).
_TRIGGER_MOTIVE_EVENT_KINDS: dict[str, str] = {
    TRIGGER_DRAFT_GENERATED: "draft_generated",
}

#: Business-event triggers wired into the free-will choice pipeline (S4).
#: These are exactly the registered N1 triggers that core/choice.py knows a
#: topic for. Any other trigger (custom registrations, future business
#: events) keeps the legacy deterministic path, so behavior and contracts
#: stay unchanged until the trigger is deliberately wired in.
_CHOICE_WIRED_TRIGGERS: frozenset[str] = frozenset(
    {
        TRIGGER_DRAFT_GENERATED,
        TRIGGER_DRAFT_REVISED,
        TRIGGER_DRAFT_GATE_PASSED,
        TRIGGER_STYLE_SET,
        TRIGGER_PLOT_PLANTED,
        TRIGGER_TALK_FIRST_ROUND,
    }
)


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


def _warn_motive_llm_unavailable() -> None:
    """Print the N28 placeholder warning once per process, never spam."""
    global _motive_llm_warning_shown
    if not _motive_llm_warning_shown:
        print(MOTIVE_LLM_WARNING, file=sys.stderr)
        _motive_llm_warning_shown = True


def _sediment_motive(
    db: DB,
    workspace_id: str,
    trigger: str,
    context: TriggerContext,
) -> None:
    """Sediment a motive for the event when a deterministic rule exists."""
    event_kind = _TRIGGER_MOTIVE_EVENT_KINDS.get(trigger)
    if event_kind is None:
        return
    derive_motives(db, workspace_id, event_kind, dict(context))


def _load_choice_inputs(
    db: DB,
    workspace_id: str,
) -> tuple[
    dict[str, str],
    dict[str, choice.PersonalityParams],
    list[AgentMotive],
    dict[str, choice.FeedbackCounts],
]:
    """Load the choice-pipeline inputs keyed by agent name (the proactive key space).

    Returns (agents: name -> role, params: name -> personality, motives,
    feedback). Motives and feedback are stored keyed by agent id, so they are
    re-keyed to names here; choice only reads kind/content/strength from a
    motive and the count fields from feedback, and the lightweight
    AgentMotive projections are never persisted.
    """
    agents = list_agents(db, workspace_id)
    names_by_id = {agent.id: agent.name for agent in agents}
    roles = {agent.name: agent.role for agent in agents}
    params = {
        agent.name: choice.PersonalityParams(
            proactivity=agent.proactivity,
            stubbornness=agent.stubbornness,
            talkativeness=agent.talkativeness,
            patience=agent.patience,
        )
        for agent in agents
    }
    motives = [
        AgentMotive(
            workspace_id=motive.workspace_id,
            agent_id=names_by_id.get(motive.agent_id, motive.agent_id),
            kind=motive.kind,
            content=motive.content,
            strength=motive.strength,
            source=motive.source,
        )
        for motive in list_motives(db, workspace_id)
    ]
    feedback = {
        names_by_id.get(agent_id, agent_id): counts
        for agent_id, counts in choice.load_feedback_counts(db, workspace_id).items()
    }
    return roles, params, motives, feedback


def evaluate_proactive_triggers(
    db: DB,
    workspace_id: str,
    trigger: str,
    context: TriggerContext | None = None,
) -> list[ProactiveCandidate]:
    """Evaluate one situation and return the candidates that should fire.

    A disabled switch returns no candidates (fully silent), and partners over
    their per-workspace budget are skipped. Wired business triggers run the
    free-will pipeline - sedimenting a motive when the trigger has a rule,
    then coarse-filter -> weights -> weighted pick with dial/seed from
    Settings; other triggers keep the legacy deterministic path. No messages
    are written here; only motives may be sedimented.
    """
    if not db.settings.proactive_enabled:
        return []
    if db.settings.motive_llm_enabled:
        _warn_motive_llm_unavailable()
    context = context if context is not None else {}
    specs = _PROACTIVE_TRIGGERS.get(trigger, [])
    if not specs:
        return []
    # The event itself sediments a motive (when a rule exists) regardless of
    # whether a message fires; motives are event facts, not message choices.
    _sediment_motive(db, workspace_id, trigger, context)
    eligible = [spec for spec in specs if spec.condition(context)]
    if not eligible:
        return []
    if trigger not in _CHOICE_WIRED_TRIGGERS:
        return _legacy_evaluate(db, workspace_id, eligible)
    agents_by_name, params, motives, feedback = _load_choice_inputs(
        db, workspace_id
    )
    remaining_budget: dict[str, int] = {}

    def _budget_left(agent: str) -> bool:
        if agent not in remaining_budget:
            remaining_budget[agent] = (
                db.settings.proactive_max_per_agent
                - count_proactive_messages(db, workspace_id, agent)
            )
        return remaining_budget[agent] > 0

    candidates: list[ProactiveCandidate] = []
    choice_candidates: list[choice.ChoiceCandidate] = []
    for spec in eligible:
        if not _budget_left(spec.agent):
            continue
        if spec.agent not in agents_by_name:
            # The choice pipeline has no role/params key space for this agent;
            # keep the legacy deterministic inclusion instead of dropping it.
            candidates.append(
                ProactiveCandidate(
                    agent=spec.agent, kind=spec.kind, content=spec.content
                )
            )
            remaining_budget[spec.agent] -= 1
            continue
        choice_candidates.append(
            choice.ChoiceCandidate(
                agent=spec.agent, kind=spec.kind, content=spec.content
            )
        )
    if choice_candidates:
        picked = choice.evaluate_choice(
            trigger,
            choice_candidates,
            agents_by_name,
            motives,
            params,
            feedback,
            dial=db.settings.freedom_dial,
            seed=db.settings.freedom_seed,
        )
        candidates.extend(
            ProactiveCandidate(
                agent=item.agent, kind=item.kind, content=item.content
            )
            for item in picked
        )
    return candidates


def _legacy_evaluate(
    db: DB,
    workspace_id: str,
    eligible: list[ProactiveSpec],
) -> list[ProactiveCandidate]:
    """Legacy deterministic path for triggers outside the choice pipeline."""
    candidates: list[ProactiveCandidate] = []
    remaining_budget: dict[str, int] = {}
    for spec in eligible:
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

    Evaluation may first sediment the event's motive (draft_generated today);
    then each firing candidate becomes an agent message carrying the standard
    proactive payload plus its agent.message event. Writes run in their own
    transaction after the business operation already committed, so a
    proactive failure can never roll the business result back; callers decide
    how to surface it.
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
