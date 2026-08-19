"""Versioned world-setting services for workspaces (N5)."""

from __future__ import annotations

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import SettingEntry, SettingVersion, Workspace

SETTING_KINDS: tuple[str, ...] = ("character", "relation", "timeline", "world")
KIND_LABELS: dict[str, str] = {
    "character": "人物",
    "relation": "关系",
    "timeline": "时间线",
    "world": "世界观",
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
        return entry


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
