"""Personality drift (N28-C S1): effective params, drift writes, lazy rebase.

The four personality parameters from N27-C are the stable profile baseline.
Behavior feedback moves a separate drift layer (per field, -10..10) instead
of rewriting the baseline itself; the effective parameter a behavior path
reads is clamp(baseline + drift, 0, 10) (09 design: drift stays bounded and
never runs wild). Drift settles lazily toward 0 on the next touch: whole days
since the last drift trace, one point per full day, never crossing 0 (N17
lazy-time philosophy - no timers, no background sweeps, time is recalled on
touch). Every drift change leaves a behavior_timeline row (kind=viewpoint,
source=drift:<event>) so the evolution is replayable and explainable.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import literal_column

from novel_editorial.core.agents import resolve_agent
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, BehaviorTimeline

#: Personality field -> drift column on the Agent row. Must mirror
#: PERSONALITY_PARAM_FIELDS / DRIFT_PARAM_FIELDS in store/models.py.
DRIFT_FIELDS: dict[str, str] = {
    "proactivity": "drift_proactivity",
    "stubbornness": "drift_stubbornness",
    "talkativeness": "drift_talkativeness",
    "patience": "drift_patience",
}

#: Drift bounds and the lazy-rebase step (one point per whole day toward 0).
DRIFT_MIN = -10
DRIFT_MAX = 10
PARAM_MIN = 0
PARAM_MAX = 10
REBASE_STEP_PER_DAY = 1

# SQLite rowid ordering: rows are append-only, so rowid desc yields the latest
# drift trace even when created_at collides within one tick.
_ROWID = literal_column("rowid")


def _drift_column(field: str) -> str:
    try:
        return DRIFT_FIELDS[field]
    except KeyError:
        expected = ", ".join(DRIFT_FIELDS)
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"unknown personality field: {field} (expected one of: {expected})",
        ) from None


def _as_utc(value: datetime) -> datetime:
    """Normalize a datetime to aware UTC (SQLite rows come back naive)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _settle_toward_zero(drift: int, days: int) -> int:
    """Move drift one point per whole day toward 0, never crossing it."""
    if days <= 0:
        return drift
    steps = days * REBASE_STEP_PER_DAY
    if drift > 0:
        return max(0, drift - steps)
    if drift < 0:
        return min(0, drift + steps)
    return drift


def effective_param(agent: Agent, field: str) -> int:
    """Return the effective personality value: clamp(baseline + drift, 0, 10)."""
    column = _drift_column(field)
    baseline = int(getattr(agent, field))
    drift = int(getattr(agent, column))
    return _clamp(baseline + drift, PARAM_MIN, PARAM_MAX)


def apply_param_drift(
    db: DB,
    workspace_id: str,
    agent_id: str,
    field: str,
    delta: int,
    *,
    event: str = "apply",
) -> BehaviorTimeline:
    """Apply one drift step and leave an atomic behavior-timeline trace.

    The new drift is clamp(current + delta, -10, 10). The agent update and the
    trace commit in one workspace transaction, so a drift write can never
    exist without its explainable source. ``event`` names the feedback that
    caused the drift and is embedded in ``source=drift:<event>``.
    """
    column = _drift_column(field)
    if isinstance(delta, bool) or not isinstance(delta, int):
        raise NovelError(
            ErrorCode.USAGE_ERROR, f"delta must be an integer, got {delta!r}"
        )
    agent = resolve_agent(db, workspace_id, agent_id)
    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, id=agent.id)
            .first()
        )
        if row is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"agent not found: {agent_id}")
        before = int(getattr(row, column))
        after = _clamp(before + delta, DRIFT_MIN, DRIFT_MAX)
        setattr(row, column, after)
        entry = BehaviorTimeline(
            workspace_id=workspace_id,
            agent_id=row.id,
            kind="viewpoint",
            target=field,
            summary=(
                f"{field} drift {before:+d} -> {after:+d} "
                f"(delta {delta:+d}, event={event})"
            ),
            before_value=str(before),
            after_value=str(after),
            source=f"drift:{event}",
        )
        session.add(entry)
        session.commit()
        return entry


def rebase_param_drift(
    db: DB,
    workspace_id: str,
    agent_id: str,
    now: datetime | None = None,
) -> dict[str, int]:
    """Settle drift toward 0 by whole days since the last drift touch.

    One point per full day, both signs, never crossing 0. The settlement and
    its trace commit atomically, and the trace itself becomes the new touch
    time, so re-running with the same ``now`` is a no-op (idempotent); later
    runs only settle what the extra whole days moved (monotonic). Returns the
    four current drift values keyed by field.
    """
    resolved = datetime.now(UTC) if now is None else _as_utc(now)
    agent = resolve_agent(db, workspace_id, agent_id)
    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, id=agent.id)
            .first()
        )
        if row is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"agent not found: {agent_id}")
        last_touch = (
            session.query(BehaviorTimeline)
            .filter(
                BehaviorTimeline.workspace_id == workspace_id,
                BehaviorTimeline.agent_id == row.id,
                BehaviorTimeline.source.like("drift:%"),
            )
            .order_by(_ROWID.desc())
            .first()
        )
        if last_touch is None:
            return {
                field: int(getattr(row, column))
                for field, column in DRIFT_FIELDS.items()
            }
        days = max(0, (resolved - _as_utc(last_touch.created_at)).days)
        for field, column in DRIFT_FIELDS.items():
            current = int(getattr(row, column))
            settled = _settle_toward_zero(current, days)
            if settled != current:
                setattr(row, column, settled)
                session.add(
                    BehaviorTimeline(
                        workspace_id=workspace_id,
                        agent_id=row.id,
                        kind="viewpoint",
                        target=field,
                        summary=(
                            f"{field} drift rebased {current:+d} -> "
                            f"{settled:+d} ({days} day(s) toward 0)"
                        ),
                        before_value=str(current),
                        after_value=str(settled),
                        source="drift:rebase",
                    )
                )
        session.commit()
        return {
            field: int(getattr(row, column))
            for field, column in DRIFT_FIELDS.items()
        }
