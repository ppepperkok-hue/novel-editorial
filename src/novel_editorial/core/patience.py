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
- conflict: kind=conflict rows (unresolved discussion divergence). Weight 1 -
  an unresolved disagreement keeps draining patience, but slower than a direct
  override.

Pool value = clamp(effective patience - consumption, 0, 10), where effective
patience comes from core.evolution.effective_param (baseline + drift).
``pending_ignore_days`` is the event-driven "ignored" judgment: when a topic
is next touched, it recalls how many whole days the partner's pressed or
unresolved opinion has been pending. It only computes - it never scans on a
timer and never acts (automatic action stays in N29).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from sqlalchemy import and_, literal_column, or_

from novel_editorial.core.agents import list_agents, resolve_agent
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


def count_patience_states(
    db: DB, workspace_id: str, agent_id: str
) -> PatienceStateCounts:
    """Count the three patience-consuming states for one partner (read-only)."""
    with db.workspace_session(workspace_id) as session:
        rejected = (
            session.query(BehaviorTimeline)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.agent_id == agent_id,
                BehaviorTimeline.kind == "relationship",
                BehaviorTimeline.source.in_(REJECT_SOURCES),
            )
            .count()
        )
        overridden = (
            session.query(BehaviorTimeline)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.agent_id == agent_id,
                BehaviorTimeline.kind == "viewpoint",
                BehaviorTimeline.source.like(f"{OVERRIDE_SOURCE_PREFIX}%"),
            )
            .count()
        )
        conflict = (
            session.query(BehaviorTimeline)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.agent_id == agent_id,
                BehaviorTimeline.kind == CONFLICT_KIND,
            )
            .count()
        )
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
            query = query.filter(
                BehaviorTimeline.kind == "relationship",
                BehaviorTimeline.source.in_(REJECT_SOURCES),
            )
        elif state == "overridden":
            query = query.filter(
                BehaviorTimeline.kind == "viewpoint",
                BehaviorTimeline.source.like(f"{OVERRIDE_SOURCE_PREFIX}%"),
            )
        else:
            query = query.filter(BehaviorTimeline.kind == CONFLICT_KIND)
        return query.order_by(_ROWID.asc()).all()


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
    target: str,
    now: datetime | None = None,
) -> int:
    """Whole days a pressed/unresolved opinion has been pending for one topic.

    Event-driven "ignored" judgment (09 design): no countdown, no background
    scan. The caller touches the topic again and this helper recalls the
    newest override (kind=viewpoint, source=override:*) or conflict record for
    (agent, target); whole days since that record is the pending time. Zero
    when nothing is pending. N29 decides what the day threshold means - this
    stage only computes.
    """
    if not target.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "target must not be empty")
    resolve_agent(db, workspace_id, agent_id)
    resolved = datetime.now(UTC) if now is None else _as_utc(now)
    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(BehaviorTimeline)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.agent_id == agent_id,
                BehaviorTimeline.target == target,
            )
            .filter(
                or_(
                    BehaviorTimeline.kind == CONFLICT_KIND,
                    and_(
                        BehaviorTimeline.kind == "viewpoint",
                        BehaviorTimeline.source.like(f"{OVERRIDE_SOURCE_PREFIX}%"),
                    ),
                )
            )
            .order_by(_ROWID.desc())
            .first()
        )
    if row is None:
        return 0
    return max(0, (resolved - _as_utc(row.created_at)).days)
