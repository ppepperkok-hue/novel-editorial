"""Versioned world-setting services for workspaces (N5)."""

from __future__ import annotations

import sys
from datetime import datetime

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.events import EventType
from novel_editorial.store.db import DB
from novel_editorial.store.events import record_event
from novel_editorial.store.models import SettingEntry, SettingVersion, Workspace

SETTING_KINDS: tuple[str, ...] = ("character", "relation", "timeline", "world")
KIND_LABELS: dict[str, str] = {
    "character": "人物",
    "relation": "关系",
    "timeline": "时间线",
    "world": "世界观",
}
_KIND_ORDER: dict[str, int] = {
    kind: index for index, kind in enumerate(SETTING_KINDS)
}


def _ensure_workspace(db: DB, workspace_id: str) -> None:
    with db.global_session() as session:
        if session.get(Workspace, workspace_id) is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"workspace not found: {workspace_id}")


def _validate_kind(kind: str) -> None:
    if kind not in SETTING_KINDS:
        expected = ", ".join(SETTING_KINDS)
        raise NovelError(
            ErrorCode.USAGE_ERROR, f"invalid kind: {kind} (expected one of: {expected})"
        )


def _setting_sort_key(entry: SettingEntry) -> tuple[int, datetime, str]:
    """Order entries by kind order, then updated_at, then id as a tiebreak."""
    return (_KIND_ORDER[entry.kind], entry.updated_at, entry.id)


def add_setting(
    db: DB,
    workspace_id: str,
    *,
    kind: str,
    name: str,
    content: str,
    source: str = "作者",
) -> SettingEntry:
    """Create a setting entry at v1 and persist its initial version."""
    _validate_kind(kind)
    if not name.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "setting name must not be empty")
    if "".join(name.splitlines()) != name:
        raise NovelError(ErrorCode.USAGE_ERROR, "setting name must not contain newlines")
    if not content.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "setting content must not be empty")
    if not source.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "setting source must not be empty")
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        entry = SettingEntry(
            workspace_id=workspace_id,
            kind=kind,
            name=name,
            content=content,
            source=source,
            current_version=1,
        )
        session.add(entry)
        session.flush()
        session.add(
            SettingVersion(
                entry_id=entry.id,
                version=1,
                content=content,
                reason="initial",
                actor=source,
            )
        )
        session.commit()
        return entry


def list_settings(
    db: DB,
    workspace_id: str,
    kind: str | None = None,
) -> list[SettingEntry]:
    """List settings in one workspace, oldest first, id as tiebreak."""
    if kind is not None:
        _validate_kind(kind)
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        query = session.query(SettingEntry).filter_by(workspace_id=workspace_id)
        if kind is not None:
            query = query.filter_by(kind=kind)
        return list(query.order_by(SettingEntry.created_at, SettingEntry.id).all())


def get_setting(db: DB, workspace_id: str, setting_id: str) -> SettingEntry:
    """Fetch one setting entry in a workspace, or raise NOT_FOUND."""
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        entry = (
            session.query(SettingEntry)
            .filter_by(workspace_id=workspace_id, id=setting_id)
            .first()
        )
        if entry is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"setting not found: {setting_id}")
        return entry


def revise_setting(
    db: DB,
    workspace_id: str,
    setting_id: str,
    *,
    content: str,
    reason: str,
    actor: str,
) -> SettingEntry:
    """Revise a setting: bump the version and refresh current content."""
    if not content.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "setting content must not be empty")
    if not reason.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "setting reason must not be empty")
    if not actor.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "setting actor must not be empty")
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        entry = (
            session.query(SettingEntry)
            .filter_by(workspace_id=workspace_id, id=setting_id)
            .first()
        )
        if entry is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"setting not found: {setting_id}")
        entry.content = content
        entry.current_version += 1
        session.add(
            SettingVersion(
                entry_id=entry.id,
                version=entry.current_version,
                content=content,
                reason=reason,
                actor=actor,
            )
        )
        session.commit()
        name = entry.name
        version = entry.current_version
    try:
        record_event(
            db,
            workspace_id,
            type=EventType.SYSTEM,
            actor=actor,
            payload={
                "kind": "setting_revised",
                "setting_id": setting_id,
                "name": name,
                "version": version,
                "actor": actor,
                "reason": reason,
            },
        )
    except Exception as exc:
        print(f"warning: setting revision event skipped: {exc}", file=sys.stderr)
    return entry


def settings_section(db: DB, workspace_id: str) -> str:
    """Render the current-version setting block, or an empty string when empty."""
    with db.workspace_session(workspace_id) as session:
        entries = (
            session.query(SettingEntry)
            .filter_by(workspace_id=workspace_id)
            .all()
        )
    if not entries:
        return ""
    entries.sort(key=_setting_sort_key)
    lines = ["设定："]
    for entry in entries:
        label = KIND_LABELS.get(entry.kind, entry.kind)
        collapsed = " ".join(entry.content.split())
        lines.append(
            f"- [{label}] {entry.name} v{entry.current_version} "
            f"{collapsed}（来源: {entry.source}）"
        )
    return "\n".join(lines)


def check_settings(db: DB, workspace_id: str) -> str:
    """Render a deterministic report of stale and same-name conflict candidates."""
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        entries = (
            session.query(SettingEntry)
            .filter_by(workspace_id=workspace_id)
            .all()
        )
    total = len(entries)
    revised = [entry for entry in entries if entry.current_version > 1]
    revised_count = len(revised)

    lines = [f"settings: {total} entries ({revised_count} revised)"]
    if revised:
        revised.sort(key=_setting_sort_key)
        lines.append("陈旧（已修订）：")
        for entry in revised:
            label = KIND_LABELS.get(entry.kind, entry.kind)
            collapsed = " ".join(entry.content.split())
            lines.append(
                f"- {entry.name}（{label}）v{entry.current_version} {collapsed}"
                f"（来源: {entry.source}）—— 已修订，旧版本见 history"
            )

    by_name: dict[str, list[SettingEntry]] = {}
    for entry in entries:
        by_name.setdefault(entry.name, []).append(entry)
    conflict_groups = [group for group in by_name.values() if len(group) >= 2]
    if conflict_groups:
        lines.append("同名冲突：")
        for group in sorted(conflict_groups, key=lambda entries: entries[0].name):
            group.sort(
                key=lambda entry: (
                    _KIND_ORDER[entry.kind],
                    entry.current_version,
                    entry.id,
                )
            )
            parts = " 与 ".join(
                f"{KIND_LABELS.get(entry.kind, entry.kind)} v{entry.current_version}"
                for entry in group
            )
            lines.append(f"- 「{group[0].name}」：{parts} —— 同名条目，请确认是否矛盾")

    if not revised and not conflict_groups:
        return f"settings: {total} entries ({revised_count} revised)；同名冲突：无"
    return "\n".join(lines)


def list_setting_history(
    db: DB,
    workspace_id: str,
    setting_id: str,
) -> list[SettingVersion]:
    """List every version of a setting, oldest first."""
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        entry = (
            session.query(SettingEntry)
            .filter_by(workspace_id=workspace_id, id=setting_id)
            .first()
        )
        if entry is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"setting not found: {setting_id}")
        return list(
            session.query(SettingVersion)
            .filter_by(entry_id=setting_id)
            .order_by(SettingVersion.version)
            .all()
        )
