"""Cross-workspace aggregation service (N10 O1): one glance at every office.

The report is strictly read-only: it reads each workspace's public metadata
(title / genre / status / pending-draft count / structure progress / latest
activity) and never mutates any data. A workspace whose database cannot be
read is warned about on stderr and skipped; the rest still report.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import literal_column

from novel_editorial.core.structure import count_structure
from novel_editorial.store.db import DB
from novel_editorial.store.models import Draft, Event, Workspace

# SQLite assigns every events row an implicit rowid; rows are append-only, so
# rowid order equals insertion order (same cursor convention as store.events).
_ROWID = literal_column("rowid")

DRAFT_STATUS_PENDING = "draft"


@dataclass(frozen=True)
class WorkspaceOverview:
    """One workspace's aggregated summary for the cross-workspace view."""

    workspace_id: str
    title: str
    genre: str
    status: str
    pending_count: int
    structure: str
    last_activity: datetime
    created_at: datetime


@dataclass(frozen=True)
class WorkspaceOverviewReport:
    """All aggregated summaries plus skip statistics."""

    overviews: list[WorkspaceOverview]
    total: int
    skipped: int


def _as_utc(value: datetime) -> datetime:
    """Normalize a SQLite-read datetime into a UTC-aware value."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _build_overview(db: DB, workspace: Workspace) -> WorkspaceOverview:
    workspace_id = workspace.id
    with db.workspace_session(workspace_id) as session:
        pending_count = (
            session.query(Draft)
            .filter_by(workspace_id=workspace_id, status=DRAFT_STATUS_PENDING)
            .count()
        )
        latest_event_time = (
            session.query(Event.time)
            .filter_by(workspace_id=workspace_id)
            .order_by(_ROWID.desc())
            .limit(1)
            .scalar()
        )
    counts = count_structure(db, workspace_id)
    if counts["total_nodes"]:
        structure = f"{counts['completed_chapters']}/{counts['chapters']} 章"
    else:
        structure = "-"
    last_activity = (
        latest_event_time if latest_event_time is not None else workspace.created_at
    )
    return WorkspaceOverview(
        workspace_id=workspace_id,
        title=workspace.title,
        genre=workspace.genre,
        status=workspace.status,
        pending_count=pending_count,
        structure=structure,
        last_activity=_as_utc(last_activity),
        created_at=_as_utc(workspace.created_at),
    )


def build_overview(db: DB) -> WorkspaceOverviewReport:
    """Aggregate every registered workspace into a sorted read-only report.

    The global registry (workspaces table) is the source of truth, matching the
    ``works list`` command. Per-workspace read failures degrade to a stderr
    warning and are counted in ``skipped``; the rest of the report still
    completes. Overviews are ordered by last activity descending, then created
    at descending, then workspace id ascending for a deterministic tiebreak.
    """
    with db.global_session() as session:
        workspaces = session.query(Workspace).all()
    overviews: list[WorkspaceOverview] = []
    skipped = 0
    for workspace in workspaces:
        try:
            overviews.append(_build_overview(db, workspace))
        except Exception as exc:  # noqa: BLE001 - per-workspace isolation
            print(
                f"warning: overview skipped: {workspace.id}: {exc}",
                file=sys.stderr,
            )
            skipped += 1
    overviews.sort(
        key=lambda item: (
            -item.last_activity.timestamp(),
            -item.created_at.timestamp(),
            item.workspace_id,
        )
    )
    return WorkspaceOverviewReport(
        overviews=overviews,
        total=len(overviews),
        skipped=skipped,
    )
