"""N29 natural discussion: pool-bottom candidates, topic cooldown and summon.

Trigger judgment for the editorial band's natural discussion (N29): when a
partner's patience pool bottoms out (pool == 0, computed read-only from
core.patience), they become a summon candidate unless the same (agent,
target) topic is still cooling. Cooldown is lazy, exactly like the rest of
the free-will time philosophy (09 design: no timers, time is recalled at
query time, never scanned): S3 writes the kind=cooldown marker after a real
summon, and this module only recalls whether the newest marker for the pair
is still inside the cooldown window.

S1 scope: judge only. Nothing here summoned a discussion, wrote a cooldown
record or touched the business path; ``check_summon_trigger_safe`` degraded
to a stderr warning and printed a candidate hint when a trigger fired.

S2 scope (N29-B): ``summon_natural_discussion`` opens the full N4 discussion
shape - open_discussion, both sides contribute, editor-in-chief summarizes -
around the candidate's pending topic, reusing the existing deterministic
templates from core.discussion (no LLM, no new copy), then appends one
agent.message event carrying kind=natural_discussion so the author can see
the summon in `events list` (N29-F4). The summon is a collaboration chain,
never a creation chain: it writes no prose, edits no draft and never decides
for the author (red line: 创作链由作者把守).

S3 scope (N29-C): ``check_summon_trigger_safe`` stops hinting and runs the
real summon from the three accumulation paths (decision reject, talk
override, summarize divergence); after a successful round the summon writes
the kind=cooldown marker (source=discussion:summoned, target=topic,
after_value=pool summary) and clears the candidate's pool through
core.patience.clear_pool_pressure (复用 N28 RESOLVED_SOURCE 中和语义, 清零进
冷却、未解决重新攒). A reentrancy guard blocks the candidate's own round from
triggering a second summon when the N4 shape makes them refuse again (防风暴).
The whole summon stays safe-degraded: any failure only warns on stderr and
returns None, and no summon happens unless the partner is actually a
candidate (switch on, pool bottom, topic not cooling).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import TypedDict

from sqlalchemy import literal_column

from novel_editorial.core.agents import get_agent_by_id, get_default_writer, list_agents
from novel_editorial.core.behavior import record_behavior_entry
from novel_editorial.core.chat import get_agent
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.patience import (
    POOL_MIN,
    RESOLVED_SOURCE,
    clear_pool_pressure,
    patience_pool,
)
from novel_editorial.events import EventType
from novel_editorial.store.db import DB
from novel_editorial.store.events import record_event
from novel_editorial.store.models import (
    Agent,
    AgentRole,
    BehaviorTimeline,
    Decision,
    Draft,
)

#: Cooldown window in whole days for one (agent, target) topic. Comment basis
#: (09 free-will design): 清零进冷却、未解决重新攒 - after a natural summon
#: the topic enters cooldown, and only an unresolved issue that is still
#: pressing after the window may re-accumulate and trigger again. Lazy: the
#: elapsed whole days are recalled at query time (patience.pending_ignore_days
#: convention), never counted on a timer.
COOLDOWN_PERIOD_DAYS = 3

#: Behavior kind carrying the cooldown marker (S3 writes it; S1 only reads).
COOLDOWN_KIND = "cooldown"

#: Stable source written on a real natural summon (S3 contract). The S1/S2
#: reader accepts any kind=cooldown row regardless of source; the constant
#: pins the source so S3 and the readers stay consistent.
COOLDOWN_SOURCE = "discussion:summoned"

#: Stable payload contract of the natural-summon marker event (S2). The event
#: rides the agent.message channel so `events list` shows it, and pins the
#: fields the task package requires (initiator=agent, kind, trigger, agent_id,
#: topic) plus the discussion id so every summon stays traceable (可解释红线).
SUMMON_INITIATOR = "agent"
SUMMON_KIND = "natural_discussion"
SUMMON_TRIGGER = "patience_exhausted"

#: Reentrancy guard: one natural summon per (workspace, agent) at a time.
#: The N4 round's own summary runs the same trigger check for refusing
#: partners, and a conflict-driven candidate who refuses again inside the
#: round would otherwise summon recursively (M5-N29-S3-FIX). Deterministic
#: and bounded: the guard only skips the same agent while its own round is
#: still opening, and every round terminates.
_SUMMONS_IN_PROGRESS: set[tuple[str, str]] = set()

# SQLite rowid ordering: rows are append-only, so rowid desc yields the
# newest marker even when created_at collides within one tick.
_ROWID = literal_column("rowid")


def _as_utc(value: datetime) -> datetime:
    """Normalize a datetime to aware UTC (SQLite rows come back naive)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SummonCandidate(TypedDict):
    agent_id: str
    agent_name: str
    pool: int
    topic: str | None


class SummonResult(TypedDict):
    discussion_id: str
    topic: str
    agent_id: str
    counterpart: str
    summary: str


def _pending_pressure_record(
    db: DB, workspace_id: str, agent_id: str
) -> BehaviorTimeline | None:
    """Return the newest record naming the partner's pending pressure topic.

    Override rows (kind=viewpoint, source=override:*) and unresolved conflict
    rows (kind=conflict, source=discussion:unresolved) live in an issue
    namespace and can name the 议题 a natural discussion would open around.
    Rowid desc walks newest first; the first still-active record wins,
    matching ``_pending_topic`` and the patience group semantics (a newer
    discussion:resolved row closes the (agent, target) conflict group). None
    means the partner carries only rejections (or nothing at all), and the
    topic falls back to the newest decision:reject target.
    """
    with db.workspace_session(workspace_id) as session:
        rows = (
            session.query(BehaviorTimeline)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.agent_id == agent_id,
                BehaviorTimeline.kind.in_(("viewpoint", "conflict")),
            )
            .order_by(_ROWID.desc())
            .all()
        )
    latest_conflict_source: dict[str, str] = {}
    for row in rows:
        if row.kind == "conflict" and row.target not in latest_conflict_source:
            # Rows arrive newest first, so the first occurrence per target is
            # its newest record - exactly the group semantics patience uses.
            latest_conflict_source[row.target] = row.source
    for row in rows:
        if row.kind == "conflict":
            if latest_conflict_source[row.target] == RESOLVED_SOURCE:
                continue
            return row
        if row.source.startswith("override:"):
            return row
    return None


def _pending_topic(db: DB, workspace_id: str, agent_id: str) -> str | None:
    """Return the target of the partner's newest pending pressure, or None.

    Only override rows (kind=viewpoint, source=override:*) and unresolved
    conflict rows (kind=conflict, source=discussion:unresolved) live in an
    issue namespace and can name the 议题 a natural discussion would open
    around. Rejection rows target the author and carry no topic, so a partner
    drained purely by rejections falls back to the newest decision:reject
    target (chapter title) - the same (agent, target) key decision.py's reject
    trigger check and S3's cooldown write use, keeping both anti-storm entries
    on one namespace. Rowid desc walks newest first and returns the newest
    record that is still active, matching the patience group semantics (a
    newer discussion:resolved row closes the (agent, target) conflict group).
    """
    record = _pending_pressure_record(db, workspace_id, agent_id)
    if record is None:
        return _recent_reject_topic(db, workspace_id, agent_id)
    return record.target


def _recent_reject_topic(db: DB, workspace_id: str, agent_id: str) -> str | None:
    """Return the partner's newest decision:reject target (chapter title).

    The decision-reject trigger check (core.decision.decide) keys its cooldown
    check on the rejected draft's title, falling back to the draft id when the
    title is blank (``reject_target = draft.title.strip() or draft_id``).
    Reject rows in the behavior timeline target the author and carry no topic,
    so the key is recalled from the decision log instead: the newest
    action=reject decision for the partner's draft, resolved to the same
    title-or-id. S3 writes kind=cooldown with target=this key after a real
    summon, so reading it here keeps summon_candidates and the reject trigger
    check on the same (agent, target) namespace (防风暴口径一致).
    """
    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(Draft)
            .join(Decision, Decision.draft_id == Draft.id)
            .filter(
                Decision.workspace_id == workspace_id,
                Draft.workspace_id == workspace_id,
                Draft.writer_id == agent_id,
                Decision.action == "reject",
            )
            .order_by(literal_column("decisions.rowid").desc())
            .first()
        )
    if row is None:
        return None
    return row.title.strip() or row.id


def within_cooldown(
    db: DB,
    workspace_id: str,
    agent_id: str,
    target: str,
    now: datetime | None = None,
) -> bool:
    """True while the (agent, target) topic is inside its cooldown window.

    Lazy and timer-free (09 design): the newest kind=cooldown record for the
    pair is recalled at query time. A record older than COOLDOWN_PERIOD_DAYS
    (whole days, matching patience.pending_ignore_days) means the window has
    passed and the topic may re-accumulate; a missing or future-dated record
    is never within cooldown.
    """
    if not agent_id.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "agent_id must not be empty")
    if not target.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "target must not be empty")
    resolved = datetime.now(UTC) if now is None else _as_utc(now)
    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(BehaviorTimeline)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.agent_id == agent_id,
                BehaviorTimeline.kind == COOLDOWN_KIND,
                BehaviorTimeline.target == target,
            )
            .order_by(_ROWID.desc())
            .first()
        )
    if row is None:
        return False
    elapsed_days = (resolved - _as_utc(row.created_at)).days
    return 0 <= elapsed_days < COOLDOWN_PERIOD_DAYS


def is_summon_candidate(
    db: DB,
    workspace_id: str,
    *,
    agent_id: str,
    target: str,
    now: datetime | None = None,
) -> bool:
    """True when one partner is a summon candidate for one target.

    Trigger judgment (N29-A): patience pool == 0 and the (agent, target)
    topic is not inside its cooldown window. Read-only; never writes and
    never summons.
    """
    pool = patience_pool(db, workspace_id, agent_id)
    if pool["pool"] != POOL_MIN:
        return False
    return not within_cooldown(db, workspace_id, agent_id, target, now=now)


def summon_candidates(
    db: DB,
    workspace_id: str,
    now: datetime | None = None,
) -> list[SummonCandidate]:
    """Return the pool-bottom partners who may be naturally summoned.

    A partner is a candidate when their patience pool is 0 (computed
    read-only from core.patience) and their newest pending pressure topic is
    not inside the cooldown window. A partner drained purely by rejections
    carries the newest decision:reject target (chapter title) as their
    pending topic - the same (agent, target) key decision.py's reject trigger
    check uses and the same key S3 writes kind=cooldown with after a real
    summon, so both anti-storm entries consult one namespace. A partner with
    no pending topic at all (no issue rows and no reject decision log) stays
    a candidate for visibility only (topic=None) but is never summoned: the
    N4 shape opens around a 议题 and open_discussion rejects a blank topic,
    so S2 skips that partner with a stderr warning. Listing keeps the state
    observable and the S3 wiring loud instead of silent (no-topic 契约:
    可见但不可召集). The
    proactive_enabled switch gates the whole module: when off, no candidates
    (fully silent, no natural summon). Order is deterministic: candidates are
    sorted by partner name (unique per workspace), so the result is
    reproducible even when agent rows share one created_at tick and fall back
    to random id tiebreaks in list_agents.
    """
    if not db.settings.proactive_enabled:
        return []
    candidates: list[SummonCandidate] = []
    agents = sorted(list_agents(db, workspace_id), key=lambda agent: agent.name)
    for agent in agents:
        pool = patience_pool(db, workspace_id, agent.id)
        if pool["pool"] != POOL_MIN:
            continue
        topic = _pending_topic(db, workspace_id, agent.id)
        if topic is not None and within_cooldown(
            db, workspace_id, agent.id, topic, now=now
        ):
            continue
        candidates.append(
            {
                "agent_id": agent.id,
                "agent_name": agent.name,
                "pool": pool["pool"],
                "topic": topic,
            }
        )
    return candidates


def check_summon_trigger_safe(
    db: DB,
    workspace_id: str,
    *,
    agent_id: str,
    target: str,
    now: datetime | None = None,
) -> bool:
    """Run the post-event trigger check, summoning when the partner qualifies.

    Called once after the three accumulation paths (decision reject, talk
    override, summarize divergence). S1 judged and hinted; S3 wires the real
    summon: when the partner is a candidate, ``summon_natural_discussion``
    opens the N4 round around their pending topic, writes the cooldown marker
    and clears the pool (清零进冷却). Any failure is caught and only warned so
    it can never roll the business operation back (safe degrade), and the
    check returns True exactly when a natural round was actually summoned.
    The proactive_enabled switch gates the check too: when off, fully silent -
    no candidates, no hint, no summon.
    """
    if not db.settings.proactive_enabled:
        return False
    try:
        if not is_summon_candidate(
            db, workspace_id, agent_id=agent_id, target=target, now=now
        ):
            return False
        agent = get_agent_by_id(db, workspace_id, agent_id)
        if agent is None:
            return False
        return summon_natural_discussion(db, workspace_id, agent, now=now) is not None
    except Exception as exc:
        print(f"warning: natural discussion check skipped: {exc}", file=sys.stderr)
        return False


def _resolve_counterpart(
    db: DB,
    workspace_id: str,
    candidate: Agent,
    topic: str,
) -> Agent:
    """Return the other side of the candidate's pending divergence.

    The counterpart is recalled from the pending topic's records, never
    guessed (09 design: deterministic and replayable). The newest other
    partner's kind=viewpoint row sharing the topic namespace is the other
    side of the divergence: discussion sediment (core.discussion
    _trace_discussion_sediment) writes one viewpoint row per participant with
    source=discussion:<id> and target=the topic, so an unresolved conflict on
    a topic recalls who else weighed in on it. Override rows
    (source=override:<rule>) live in the rule namespace and name no band
    partner - the pressure came from the author (talk.py override path), not
    from another partner - so that branch finds nothing and falls back to the
    deterministic default pairing. The editor-in-chief is never recalled as
    the other side: N4 splits 分歧双方 and 主编通气总结, so the editor chairs
    the round instead of joining one side - sediment naming only the editor
    falls back to the default pairing (M5-N29-S2-FIX, 总编不自我总结).
    """
    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(BehaviorTimeline)
            .join(Agent, Agent.id == BehaviorTimeline.agent_id)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.kind == "viewpoint",
                BehaviorTimeline.target == topic,
                BehaviorTimeline.agent_id != candidate.id,
                Agent.role != candidate.role,
                Agent.role != AgentRole.EDITOR_IN_CHIEF,
            )
            .order_by(literal_column("behavior_timeline.rowid").desc())
            .first()
        )
    if row is not None:
        partner = get_agent_by_id(db, workspace_id, row.agent_id)
        if partner is not None:
            return partner
    return _default_counterpart(db, workspace_id, candidate)


def _default_counterpart(db: DB, workspace_id: str, candidate: Agent) -> Agent:
    """Return the deterministic default pair member for one candidate.

    依据 (12-n29-checklist 核心场景): 审稿被压到耐心耗尽时，编辑部自动召集
    一轮讨论，写手与审稿对质、主编通气总结. The creative-chain center (the
    default writer) is the counterpart for every candidate except the writer,
    whose counterpart is the reviewer.
    """
    if candidate.role == AgentRole.REVIEWER:
        return get_default_writer(db, workspace_id)
    if candidate.role == AgentRole.WRITER:
        return get_agent(db, workspace_id, AgentRole.REVIEWER)
    return get_default_writer(db, workspace_id)


def summon_natural_discussion(
    db: DB,
    workspace_id: str,
    agent: Agent,
    now: datetime | None = None,
) -> SummonResult | None:
    """Open one natural discussion round around the partner's pending topic.

    The candidate is one side of the divergence; the other side is recalled
    from the pending topic's records (fallback: 写手/审稿 default pairing,
    see _resolve_counterpart), and the editor-in-chief summarizes. The round
    runs the full N4 shape through the existing deterministic templates:
    open_discussion -> both sides contribute -> summarize_discussion. No prose
    is written, no draft is edited and no decision is made for the author
    (red line: 讨论是协作链，创作链由作者把守). After the summary, one
    agent.message event with kind=natural_discussion marks the summon so the
    author can see it in `events list` (N29-F4).

    Safe-degraded like the S1 trigger check: any failure only warns on stderr
    and returns None, so the calling business operation can never be rolled
    back. No summon happens unless the partner is actually a candidate: the
    proactive_enabled switch gates the module (关掉全静默), the pool must be
    bottom, and a cooling topic is skipped. A partner with no pending topic at
    all stays visible in summon_candidates (topic=None) but is not summoned
    here - the N4 shape opens around a 议题 and open_discussion rejects a
    blank topic, so the summon side skips with a warning instead of staying
    silent (S3 接线不静默). The editor-in-chief never joins as one of the two
    sides: N4 splits 分歧双方 and 主编通气总结, so a pool-bottom editor
    candidate is skipped with a warning - the editor chairs the round and
    must not summarize their own stance (M5-N29-S2-FIX).

    S3 (N29-C): after the round and the marker event succeed, the summon
    writes the kind=cooldown marker (source=discussion:summoned, target=topic,
    after_value=pool summary) and clears the candidate's pool via
    core.patience.clear_pool_pressure - the same append-only RESOLVED_SOURCE
    neutralization N28 uses, so 清零进冷却 and 未解决重新攒 stay replayable.
    A reentrancy guard keeps the round itself from re-summoning: when the N4
    shape makes the candidate refuse again on an unresolved topic, the inner
    trigger check sees the same (workspace, agent) summon already in progress
    and skips with a warning (防风暴).
    """
    if not db.settings.proactive_enabled:
        return None
    try:
        if agent.role == AgentRole.EDITOR_IN_CHIEF:
            # N4 形状: 点将分歧双方 + 主编通气总结. The editor-in-chief
            # chairs the round and summarizes neutrally; letting the editor
            # join one side would make the editor summarize their own stance
            # (M5-N29-S2-FIX), so a pool-bottom editor candidate is skipped
            # with a visible warning.
            print(
                "warning: natural discussion summon skipped: "
                "editor-in-chief chairs the round and never joins a side",
                file=sys.stderr,
            )
            return None
        topic = _pending_topic(db, workspace_id, agent.id)
        pool = patience_pool(db, workspace_id, agent.id)["pool"]
        if pool != POOL_MIN:
            print(
                "warning: natural discussion summon skipped: pool not bottom",
                file=sys.stderr,
            )
            return None
        if topic is None:
            print(
                "warning: natural discussion summon skipped: no pending topic",
                file=sys.stderr,
            )
            return None
        if within_cooldown(db, workspace_id, agent.id, topic, now=now):
            print(
                "warning: natural discussion summon skipped: topic in cooldown",
                file=sys.stderr,
            )
            return None
        summon_key = (workspace_id, agent.id)
        if summon_key in _SUMMONS_IN_PROGRESS:
            print(
                "warning: natural discussion summon skipped: already in progress",
                file=sys.stderr,
            )
            return None
        # Imported inside the function: discussion.py imports
        # check_summon_trigger_safe from this module, so a module-level import
        # here would form an import cycle (core -> core is legal, cycles are
        # not).
        from novel_editorial.core.discussion import (
            contribute_to_discussion,
            open_discussion,
            summarize_discussion,
        )

        counterpart = _resolve_counterpart(db, workspace_id, agent, topic)
        summarizer = get_agent(db, workspace_id, AgentRole.EDITOR_IN_CHIEF)
        _SUMMONS_IN_PROGRESS.add(summon_key)
        try:
            discussion_id, _ = open_discussion(
                db, workspace_id, topic=topic, participants=[agent, counterpart]
            )
            contribute_to_discussion(
                db, workspace_id, discussion_id=discussion_id, topic=topic, agent=agent
            )
            contribute_to_discussion(
                db,
                workspace_id,
                discussion_id=discussion_id,
                topic=topic,
                agent=counterpart,
            )
            summary = summarize_discussion(
                db,
                workspace_id,
                discussion_id=discussion_id,
                topic=topic,
                summarizer=summarizer,
            )
            record_event(
                db,
                workspace_id,
                type=EventType.AGENT_MESSAGE,
                actor=agent.name,
                payload={
                    "initiator": SUMMON_INITIATOR,
                    "kind": SUMMON_KIND,
                    "trigger": SUMMON_TRIGGER,
                    "agent_id": agent.id,
                    "topic": topic,
                    "discussion_id": discussion_id,
                },
            )
            # S3: cooldown write-back + pool clearing (清零进冷却). The pool
            # summary is recalled right before the clear so the cooldown row
            # documents the pre-clear ledger, including any conflict the round
            # itself just refused into.
            pool_detail = patience_pool(db, workspace_id, agent.id)
            states = pool_detail["states"]
            record_behavior_entry(
                db,
                workspace_id,
                agent_id=agent.id,
                kind=COOLDOWN_KIND,
                target=topic,
                summary="自然召集后议题进入冷却",
                after_value=(
                    f"pool={pool_detail['pool']} "
                    f"(rejected={states['rejected']} "
                    f"overridden={states['overridden']} conflict={states['conflict']})"
                ),
                source=COOLDOWN_SOURCE,
            )
            clear_pool_pressure(db, workspace_id, agent_id=agent.id, topic=topic)
        finally:
            _SUMMONS_IN_PROGRESS.discard(summon_key)
        return {
            "discussion_id": discussion_id,
            "topic": topic,
            "agent_id": agent.id,
            "counterpart": counterpart.name,
            "summary": summary.content,
        }
    except Exception as exc:
        print(f"warning: natural discussion summon skipped: {exc}", file=sys.stderr)
        return None
