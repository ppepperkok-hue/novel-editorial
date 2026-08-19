"""Setting impact analysis for one workspace (N18 L1)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from novel_editorial.core.plot import KIND_LABELS as PLOT_KIND_LABELS
from novel_editorial.core.setting import KIND_LABELS as SETTING_KIND_LABELS
from novel_editorial.core.setting import get_setting
from novel_editorial.store.db import DB
from novel_editorial.store.models import (
    Agent,
    AgentMemory,
    Draft,
    DraftVersion,
    Message,
    PlotThread,
    Review,
    SettingEntry,
)

SNIPPET_MAX_CHARS = 60
CONTENT_FRAGMENT_LIMIT = 5
CONTENT_FALLBACK_CHARS = 20


@dataclass
class SettingImpactItem:
    """One impacted row: layer label, source citation, and folded snippet."""

    layer: str
    source: str
    snippet: str


@dataclass
class SettingImpactReport:
    """Impact report for one setting: identity, total hits, and the limited list."""

    setting_kind: str
    setting_name: str
    setting_version: int
    total: int
    impacts: list[SettingImpactItem]


def extract_keywords(name: str, content: str) -> list[str]:
    """Build the impact keyword set for one setting.

    The full setting name is one keyword; content keywords are whitespace
    tokens of at least two characters, deduplicated in first-seen order and
    sorted by length descending before the top five are kept. When no token
    survives, the folded content prefix (20 chars) is used instead. The final
    list is deduplicated with the name first.
    """
    folded = " ".join(content.split())
    fragments: list[str] = []
    for token in folded.split():
        if len(token) >= 2 and token not in fragments:
            fragments.append(token)
    fragments.sort(key=len, reverse=True)
    if not fragments and folded:
        fragments = [folded[:CONTENT_FALLBACK_CHARS]]
    keywords: list[str] = []
    for keyword in ([name] if name.strip() else []) + fragments[:CONTENT_FRAGMENT_LIMIT]:
        if keyword not in keywords:
            keywords.append(keyword)
    return keywords


def _fold_snippet(content: str) -> str:
    """Fold whitespace and truncate to 60 chars with a trailing ellipsis."""
    collapsed = " ".join(content.split())
    if len(collapsed) <= SNIPPET_MAX_CHARS:
        return collapsed
    return collapsed[:SNIPPET_MAX_CHARS] + "…"


def _like_contains(column: Any, needle: str) -> Any:
    """Case-insensitive literal substring predicate with LIKE wildcard escaping."""
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return func.lower(column).like(f"%{escaped}%", escape="\\")


def _matches_any(column: Any, needles: list[str]) -> Any:
    """Return a predicate matching any case-insensitive literal substring."""
    return or_(*[_like_contains(column, needle) for needle in needles])


def _query_versions(
    session: Session,
    workspace_id: str,
    needles: list[str],
    exclude_id: str,
) -> list[SettingImpactItem]:
    rows = (
        session.query(DraftVersion, Draft.title)
        .join(Draft, Draft.id == DraftVersion.draft_id)
        .filter(
            Draft.workspace_id == workspace_id,
            _matches_any(DraftVersion.content, needles),
        )
        .order_by(DraftVersion.created_at.desc(), DraftVersion.id.desc())
        .all()
    )
    return [
        SettingImpactItem(
            layer="版本",
            source=f"{title} v{version.version}",
            snippet=_fold_snippet(version.content),
        )
        for version, title in rows
    ]


def _query_messages(
    session: Session,
    workspace_id: str,
    needles: list[str],
    exclude_id: str,
) -> list[SettingImpactItem]:
    rows = (
        session.query(Message)
        .filter_by(workspace_id=workspace_id)
        .filter(_matches_any(Message.content, needles))
        .order_by(Message.created_at.desc(), Message.id.desc())
        .all()
    )
    return [
        SettingImpactItem(
            layer="对话",
            source=row.actor,
            snippet=_fold_snippet(row.content),
        )
        for row in rows
    ]


def _query_reviews(
    session: Session,
    workspace_id: str,
    needles: list[str],
    exclude_id: str,
) -> list[SettingImpactItem]:
    rows = (
        session.query(Review)
        .filter_by(workspace_id=workspace_id)
        .filter(_matches_any(Review.content, needles))
        .order_by(Review.created_at.desc(), Review.id.desc())
        .all()
    )
    return [
        SettingImpactItem(
            layer="意见",
            source=f"{row.actor} 的意见",
            snippet=_fold_snippet(row.content),
        )
        for row in rows
    ]


def _query_threads(
    session: Session,
    workspace_id: str,
    needles: list[str],
    exclude_id: str,
) -> list[SettingImpactItem]:
    rows = (
        session.query(PlotThread)
        .filter_by(workspace_id=workspace_id)
        .filter(_matches_any(PlotThread.content, needles))
        .order_by(PlotThread.updated_at.desc(), PlotThread.id.desc())
        .all()
    )
    return [
        SettingImpactItem(
            layer="线索",
            source=f"伏笔：{PLOT_KIND_LABELS.get(row.kind, row.kind)}",
            snippet=_fold_snippet(row.content),
        )
        for row in rows
    ]


def _query_notes(
    session: Session,
    workspace_id: str,
    needles: list[str],
    exclude_id: str,
) -> list[SettingImpactItem]:
    rows = (
        session.query(AgentMemory, Agent.name)
        .outerjoin(
            Agent,
            (Agent.id == AgentMemory.agent_id)
            & (Agent.workspace_id == AgentMemory.workspace_id),
        )
        .filter(
            AgentMemory.workspace_id == workspace_id,
            AgentMemory.archived_at.is_(None),
            _matches_any(AgentMemory.content, needles),
        )
        .order_by(AgentMemory.created_at.desc(), AgentMemory.id.desc())
        .all()
    )
    return [
        SettingImpactItem(
            layer="笔记",
            source=owner_name if owner_name is not None else note.agent_id,
            snippet=_fold_snippet(note.content),
        )
        for note, owner_name in rows
    ]


def _query_settings(
    session: Session,
    workspace_id: str,
    needles: list[str],
    exclude_id: str,
) -> list[SettingImpactItem]:
    rows = (
        session.query(SettingEntry)
        .filter_by(workspace_id=workspace_id)
        .filter(
            SettingEntry.id != exclude_id,
            or_(
                _matches_any(SettingEntry.name, needles),
                _matches_any(SettingEntry.content, needles),
            ),
        )
        .order_by(SettingEntry.updated_at.desc(), SettingEntry.id.desc())
        .all()
    )
    return [
        SettingImpactItem(
            layer="设定",
            source=f"{row.name}（{SETTING_KIND_LABELS.get(row.kind, row.kind)}）",
            snippet=_fold_snippet(row.content),
        )
        for row in rows
    ]


LayerQuery = Callable[[Session, str, list[str], str], list[SettingImpactItem]]


def analyze_setting_impact(
    db: DB,
    workspace_id: str,
    setting_id: str,
    limit: int = 20,
) -> SettingImpactReport:
    """Report which layers reference one setting and how (N18 L1).

    The setting itself (and its history versions, which are not searched) is
    excluded. Layers run in fixed order with per-layer time-descending order;
    the report truncates to ``limit`` and reports the pre-truncation total. A
    single failing layer warns on stderr and is skipped, never failing the
    whole report.
    """
    entry = get_setting(db, workspace_id, setting_id)
    needles = extract_keywords(entry.name, entry.content)
    if limit < 0:
        limit = 0
    impacts: list[SettingImpactItem] = []
    layer_queries: tuple[tuple[str, LayerQuery], ...] = (
        ("版本", _query_versions),
        ("对话", _query_messages),
        ("意见", _query_reviews),
        ("线索", _query_threads),
        ("笔记", _query_notes),
        ("设定", _query_settings),
    )
    with db.workspace_session(workspace_id) as session:
        for layer, query in layer_queries:
            try:
                impacts.extend(query(session, workspace_id, needles, entry.id))
            except Exception as exc:  # noqa: BLE001 - one layer must never fail the report
                session.rollback()
                print(
                    f"warning: impact layer skipped: {layer}: {exc}",
                    file=sys.stderr,
                )
    return SettingImpactReport(
        setting_kind=entry.kind,
        setting_name=entry.name,
        setting_version=entry.current_version,
        total=len(impacts),
        impacts=impacts[:limit],
    )
