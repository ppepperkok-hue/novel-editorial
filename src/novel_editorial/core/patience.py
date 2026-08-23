"""N28-E S4 patience pool: three-state counts, pool value, lazy ignore judgment.

The patience pool answers "how much longer can this partner be pushed before
they act" without a timer or a background sweep (09 design: time is recalled,
not scanned). Every input is read from the append-only behavior_timeline at
query time - no new table. Three states consume patience, each weighted:

- rejected: relationship rows sourced from decision:reject or
  delegation:refused. Weight 1 - a rejection is ordinary feedback and costs
  little on its own.
- overridden: viewpoint rows whose source starts with override:. Weight 3 -
  the author directly overrode the partner's held stance, the strongest single
  pressure; the 11-n28-checklist scenario (reviewer patience 7, three
  overrides) bottoms the pool at 0 exactly.
- conflict: kind=conflict rows whose (agent, target) group is not closed by
  its newest discussion:resolved neutralization record (unresolved discussion
  divergence). Weight 1 - an unresolved disagreement keeps draining patience,
  but slower than a direct override.

All three states follow the same append-only group semantics: a (agent,
target) group is open while its newest row is not a source=discussion:resolved
neutralization record, and closed groups stop consuming while the full history
stays replayable. N28 closes conflict groups when the author concludes the
round; N29-S3 reuses the same neutralization (``clear_pool_pressure``) to
clear the summoned partner's pool (清零进冷却、未解决重新攒).

Pool value = clamp(effective patience - consumption, 0, 10), where effective
patience comes from core.evolution.effective_param (baseline + drift).
``pending_ignore_days`` is the event-driven "ignored" judgment: when a topic
is next touched, it recalls how many whole days the partner's pressed or
unresolved opinion has been pending. Override rows live in the rule namespace
(target=rule id, source=override:<rule>) while conflict rows live in the topic
namespace (target=topic), so both namespaces are queried and the newest active
record wins. It only computes - it never scans on a timer and never acts
(automatic action stays in N29).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from sqlalchemy import and_, literal_column, or_

from novel_editorial.core.agents import list_agents, resolve_agent
from novel_editorial.core.behavior import record_behavior_entry_safe
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.evolution import effective_param
from novel_editorial.store.db import DB
from novel_editorial.store.models import BehaviorTimeline

#: Relationship sources that count as a rejection of one partner.
REJECT_SOURCES: tuple[str, ...] = ("decision:reject", "delegation:refused")

#: Viewpoint sources beginning with this prefix mean the author pressed the
#: partner's held stance down (see cli/talk.py override path).
OVERRIDE_SOURCE_PREFIX = "override:"

#: Behavior kind carrying unresolved discussion divergence (N28-E S4).
CONFLICT_KIND = "conflict"

#: Neutralization source appended when an author decision resolves a
#: discussion: the row keeps the append-only timeline replayable while pool
#: counting and the pending-days judgment treat it as no longer unresolved.
RESOLVED_SOURCE = "discussion:resolved"

#: State keys in display order; weights justify the per-state cost.
STATE_KEYS: tuple[str, ...] = ("rejected", "overridden", "conflict")
REJECTED_WEIGHT = 1
OVERRIDDEN_WEIGHT = 3
CONFLICT_WEIGHT = 1
WEIGHTS: dict[str, int] = {
    "rejected": REJECTED_WEIGHT,
    "overridden": OVERRIDDEN_WEIGHT,
    "conflict": CONFLICT_WEIGHT,
}

POOL_MIN = 0
POOL_MAX = 10

# SQLite rowid ordering: rows are append-only, so rowid desc yields the latest
# pending record even when created_at collides within one tick.
_ROWID = literal_column("rowid")


class PatienceStateCounts(TypedDict):
    rejected: int
    overridden: int
    conflict: int


class PatiencePool(TypedDict):
    agent_id: str
    agent_name: str
    effective_patience: int
    states: PatienceStateCounts
    consumption: int
    pool: int
    entries: dict[str, list[BehaviorTimeline]]


def _as_utc(value: datetime) -> datetime:
    """Normalize a datetime to aware UTC (SQLite rows come back naive)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _open_targets(rows: list[BehaviorTimeline]) -> set[str]:
    """Targets whose newest row is not a neutralization record.

    Group semantics shared by every pool state (N28 conflict + N29-S3 clear):
    rows are append-only, so a (agent, target) group is open while its newest
    row is not source=discussion:resolved. A newer neutralization closes the
    whole group without deleting history; a newer pressure row reopens it, so
    re-accumulated pressure starts counting again (未解决重新攒).
    """
    latest: dict[str, str] = {}
    for row in rows:
        latest[row.target] = row.source
    return {target for target, source in latest.items() if source != RESOLVED_SOURCE}


def count_patience_states(
    db: DB, workspace_id: str, agent_id: str
) -> PatienceStateCounts:
    """Count the three patience-consuming states for one partner (read-only).

    Every state follows the same append-only group semantics: all rows of the
    state's kind are read, and a (agent, target) group is open only while its
    newest record is not a neutralization record (source=discussion:resolved).
    A concluded divergence - or a naturally summoned topic (N29-S3) -
    therefore stops consuming patience without deleting history, and a newer
    pressure row reopens the group.
    """
    with db.workspace_session(workspace_id) as session:
        relationship_rows = (
            session.query(BehaviorTimeline)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.agent_id == agent_id,
                BehaviorTimeline.kind == "relationship",
            )
            .order_by(_ROWID.asc())
            .all()
        )
        viewpoint_rows = (
            session.query(BehaviorTimeline)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.agent_id == agent_id,
                BehaviorTimeline.kind == "viewpoint",
            )
            .order_by(_ROWID.asc())
            .all()
        )
        conflict_rows = (
            session.query(BehaviorTimeline)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.agent_id == agent_id,
                BehaviorTimeline.kind == CONFLICT_KIND,
            )
            .order_by(_ROWID.asc())
            .all()
        )
    open_relationships = _open_targets(relationship_rows)
    open_viewpoints = _open_targets(viewpoint_rows)
    open_conflicts = _open_targets(conflict_rows)
    rejected = sum(
        1
        for row in relationship_rows
        if row.target in open_relationships and row.source in REJECT_SOURCES
    )
    overridden = sum(
        1
        for row in viewpoint_rows
        if row.target in open_viewpoints
        and row.source.startswith(OVERRIDE_SOURCE_PREFIX)
    )
    conflict = sum(1 for row in conflict_rows if row.target in open_conflicts)
    return {"rejected": rejected, "overridden": overridden, "conflict": conflict}


def patience_consumption(states: PatienceStateCounts) -> int:
    """Weighted sum of the three state counts."""
    return sum(states[state] * WEIGHTS[state] for state in STATE_KEYS)


def _state_entries(
    db: DB, workspace_id: str, agent_id: str, state: str
) -> list[BehaviorTimeline]:
    """Return the underlying timeline rows for one state, oldest first."""
    with db.workspace_session(workspace_id) as session:
        query = session.query(BehaviorTimeline).filter_by(
            workspace_id=workspace_id, agent_id=agent_id
        )
        if state == "rejected":
            rows = (
                query.filter(BehaviorTimeline.kind == "relationship")
                .order_by(_ROWID.asc())
                .all()
            )
            open_targets = _open_targets(rows)
            return [
                row
                for row in rows
                if row.target in open_targets and row.source in REJECT_SOURCES
            ]
        elif state == "overridden":
            rows = (
                query.filter(BehaviorTimeline.kind == "viewpoint")
                .order_by(_ROWID.asc())
                .all()
            )
            open_targets = _open_targets(rows)
            return [
                row
                for row in rows
                if row.target in open_targets
                and row.source.startswith(OVERRIDE_SOURCE_PREFIX)
            ]
        else:
            rows = (
                query.filter(BehaviorTimeline.kind == CONFLICT_KIND)
                .order_by(_ROWID.asc())
                .all()
            )
            open_targets = _open_targets(rows)
            return [row for row in rows if row.target in open_targets]


def clear_pool_pressure(
    db: DB,
    workspace_id: str,
    *,
    agent_id: str,
    topic: str,
) -> bool:
    """Close the summoned partner's pool-consuming groups (N29-S3 池清零).

    After a natural discussion summon succeeds, the partner's accumulated
    pressure must clear so the pool can re-accumulate (09 design: 清零进冷却、
    未解决重新攒). Append-only like every N28 reset: each open group is closed
    by one source=discussion:resolved neutralization row in the same (kind,
    target) namespace, and counting treats a group as open only while its
    newest row is not a neutralization.

    - conflict rows on the topic: the exact N28 RESOLVED_SOURCE reuse;
    - override viewpoint rows on the topic (topic == rule id namespace): one
      neutralization closes the rule group, so an override-drained partner's
      pool restores to the effective patience;
    - reject relationship rows: those rows carry no topic namespace (they
      target the author or the delegating partner), so every open reject
      group of the summoned partner closes.

    Post-hoc sediment, safe-degraded like every N3 trace: each append runs
    through ``record_behavior_entry_safe``, so a failure only warns and never
    rolls the summon back. Returns True when at least one group was actually
    closed, False when the partner carried no clearable pressure.
    """
    resolve_agent(db, workspace_id, agent_id)
    if not topic.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "topic must not be empty")
    with db.workspace_session(workspace_id) as session:
        relationship_rows = (
            session.query(BehaviorTimeline)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.agent_id == agent_id,
                BehaviorTimeline.kind == "relationship",
            )
            .order_by(_ROWID.asc())
            .all()
        )
        viewpoint_rows = (
            session.query(BehaviorTimeline)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.agent_id == agent_id,
                BehaviorTimeline.kind == "viewpoint",
            )
            .order_by(_ROWID.asc())
            .all()
        )
        conflict_rows = (
            session.query(BehaviorTimeline)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.agent_id == agent_id,
                BehaviorTimeline.kind == CONFLICT_KIND,
            )
            .order_by(_ROWID.asc())
            .all()
        )
    closed = False
    open_conflicts = _open_targets(conflict_rows)
    if topic in open_conflicts:
        record_behavior_entry_safe(
            db,
            workspace_id,
            agent_id=agent_id,
            kind=CONFLICT_KIND,
            target=topic,
            summary=f"自然召集后「{topic}」分歧清零，池不再累积该议题",
            after_value="分歧清零（自然召集）",
            source=RESOLVED_SOURCE,
        )
        closed = True
    open_viewpoints = _open_targets(viewpoint_rows)
    if topic in open_viewpoints and any(
        row.target == topic and row.source.startswith(OVERRIDE_SOURCE_PREFIX)
        for row in viewpoint_rows
    ):
        record_behavior_entry_safe(
            db,
            workspace_id,
            agent_id=agent_id,
            kind="viewpoint",
            target=topic,
            summary="自然召集后立场压力清零",
            after_value="清零（自然召集）",
            source=RESOLVED_SOURCE,
        )
        closed = True
    open_relationships = _open_targets(relationship_rows)
    for target in open_relationships:
        if any(
            row.target == target and row.source in REJECT_SOURCES
            for row in relationship_rows
        ):
            record_behavior_entry_safe(
                db,
                workspace_id,
                agent_id=agent_id,
                kind="relationship",
                target=target,
                summary="自然召集后被拒压力清零",
                after_value="清零（自然召集）",
                source=RESOLVED_SOURCE,
            )
            closed = True
    return closed


def patience_pool(db: DB, workspace_id: str, agent_id: str) -> PatiencePool:
    """Return one partner's pool detail: effective patience, states and value."""
    agent = resolve_agent(db, workspace_id, agent_id)
    effective = effective_param(agent, "patience")
    states = count_patience_states(db, workspace_id, agent.id)
    consumption = patience_consumption(states)
    return {
        "agent_id": agent.id,
        "agent_name": agent.name,
        "effective_patience": effective,
        "states": states,
        "consumption": consumption,
        "pool": _clamp(effective - consumption, POOL_MIN, POOL_MAX),
        "entries": {
            state: _state_entries(db, workspace_id, agent.id, state)
            for state in STATE_KEYS
        },
    }


def patience_pools(db: DB, workspace_id: str) -> list[PatiencePool]:
    """Return every partner's pool detail, ordered by band creation."""
    agents = list_agents(db, workspace_id)
    return [patience_pool(db, workspace_id, agent.id) for agent in agents]


def pending_ignore_days(
    db: DB,
    workspace_id: str,
    agent_id: str,
    topic: str,
    rule: str | None = None,
    now: datetime | None = None,
) -> int:
    """Whole days a pressed/unresolved opinion has been pending for one topic.

    Event-driven "ignored" judgment (09 design): no countdown, no background
    scan. The caller touches the topic again and this helper recalls the
    newest active pressure record for the partner in either namespace:

    - override rows (kind=viewpoint, source=override:<rule>) live in the rule
      namespace and are matched by rule id through their source, not by
      target;
    - conflict rows (kind=conflict, target=topic) live in the topic namespace
      and are matched by target.

    Whole days since the newest active record is the pending time. A
    neutralization row (kind=conflict, source=discussion:resolved) newer than
    every conflict for the topic means the divergence is resolved: only an
    override can still be pending. Zero when nothing is pending. N29 decides
    what the day threshold means - this stage only computes.
    """
    if not topic.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "topic must not be empty")
    resolve_agent(db, workspace_id, agent_id)
    resolved = datetime.now(UTC) if now is None else _as_utc(now)
    filters = [
        and_(
            BehaviorTimeline.kind == CONFLICT_KIND,
            BehaviorTimeline.target == topic,
        )
    ]
    if rule:
        filters.append(
            and_(
                BehaviorTimeline.kind == "viewpoint",
                BehaviorTimeline.source == f"{OVERRIDE_SOURCE_PREFIX}{rule}",
            )
        )
    with db.workspace_session(workspace_id) as session:
        rows = (
            session.query(BehaviorTimeline)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.agent_id == agent_id,
                or_(*filters),
            )
            .order_by(_ROWID.desc())
            .all()
        )
    if not rows:
        return 0
    newest = rows[0]
    if newest.kind == CONFLICT_KIND and newest.source == RESOLVED_SOURCE:
        # The newest topic record is a resolution: the divergence is no longer
        # pending. Only an override in its own namespace keeps pressing, so
        # fall back to the newest override row if one exists.
        for row in rows:
            if row.kind == "viewpoint":
                return max(0, (resolved - _as_utc(row.created_at)).days)
        return 0
    return max(0, (resolved - _as_utc(newest.created_at)).days)
