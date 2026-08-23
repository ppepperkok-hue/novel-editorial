"""N29-A S1 natural discussion: pool-bottom candidates and topic cooldown.

Trigger judgment for the editorial band's natural discussion (N29): when a
partner's patience pool bottoms out (pool == 0, computed read-only from
core.patience), they become a summon candidate unless the same (agent,
target) topic is still cooling. Cooldown is lazy, exactly like the rest of
the free-will time philosophy (09 design: no timers, time is recalled at
query time, never scanned): S3 writes the kind=cooldown marker after a real
summon, and this module only recalls whether the newest marker for the pair
is still inside the cooldown window.

S1 scope: judge only. Nothing here summons a discussion, writes a cooldown
record or touches the business path. ``check_summon_trigger_safe`` degrades
to a stderr warning and prints a candidate hint when a trigger fires, so a
failure can never roll the calling business operation back (N3-style safe
degrade, same pattern as record_behavior_entry_safe).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import TypedDict

from sqlalchemy import literal_column

from novel_editorial.core.agents import list_agents
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.patience import POOL_MIN, RESOLVED_SOURCE, patience_pool
from novel_editorial.store.db import DB
from novel_editorial.store.models import BehaviorTimeline

#: Cooldown window in whole days for one (agent, target) topic. Comment basis
#: (09 free-will design): 清零进冷却、未解决重新攒 - after a natural summon
#: the topic enters cooldown, and only an unresolved issue that is still
#: pressing after the window may re-accumulate and trigger again. Lazy: the
#: elapsed whole days are recalled at query time (patience.pending_ignore_days
#: convention), never counted on a timer.
COOLDOWN_PERIOD_DAYS = 3

#: Behavior kind carrying the cooldown marker (S3 writes it; S1 only reads).
COOLDOWN_KIND = "cooldown"

#: Stable source written on a real natural summon (S3 contract). The S1
#: reader accepts any kind=cooldown row regardless of source; the constant
#: pins the source so S3 and S1 stay consistent.
COOLDOWN_SOURCE = "discussion:summoned"

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


def _pending_topic(db: DB, workspace_id: str, agent_id: str) -> str | None:
    """Return the target of the partner's newest pending pressure, or None.

    Only override rows (kind=viewpoint, source=override:*) and unresolved
    conflict rows (kind=conflict, source=discussion:unresolved) live in an
    issue namespace and can name the 议题 a natural discussion would open
    around; rejection rows target the author and carry no topic, so they
    never contribute. Rowid desc walks newest first and returns the newest
    record that is still active, matching the patience group semantics (a
    newer discussion:resolved row closes the (agent, target) conflict group).
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
            return row.target
        if row.source.startswith("override:"):
            return row.target
    return None


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
    has no pending topic - there is no (agent, target) cooldown key for them,
    so they stay candidates and S2 falls back to the default pairing. The
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
    """Run the post-event trigger check, degrading to a stderr warning.

    Called once after the three accumulation paths (decision reject, talk
    override, summarize divergence). Any failure is caught and only warned so
    it can never roll the business operation back (safe degrade). When the
    partner is a candidate, prints a single hint line - S1 judges and hints
    only; the actual summon belongs to S2. The proactive_enabled switch gates
    the check too: when off, fully silent - no candidates, no hint.
    """
    if not db.settings.proactive_enabled:
        return False
    try:
        candidate = is_summon_candidate(
            db, workspace_id, agent_id=agent_id, target=target, now=now
        )
    except Exception as exc:
        print(f"warning: natural discussion check skipped: {exc}", file=sys.stderr)
        return False
    if candidate:
        print(
            f"natural discussion candidate: agent={agent_id} target={target}"
            "（S2 自然召集待接）",
            file=sys.stderr,
        )
    return candidate
