"""Narrative thread services: plant, list, recover, and prompt injection (U20)."""

from __future__ import annotations

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import PlotThread, Workspace

KIND_FORESHADOW = "foreshadow"
KIND_GOAL = "goal"
KIND_HOOK = "hook"

VALID_KINDS: tuple[str, ...] = (KIND_FORESHADOW, KIND_GOAL, KIND_HOOK)
KIND_LABELS: dict[str, str] = {
    KIND_FORESHADOW: "伏笔",
    KIND_GOAL: "目标",
    KIND_HOOK: "钩子",
}

STATUS_PLANTED = "planted"
STATUS_PENDING = "pending"
STATUS_RECOVERED = "recovered"
STATUS_RESOLVED = "resolved"

OPEN_STATUSES: tuple[str, ...] = (STATUS_PLANTED, STATUS_PENDING)


def _ensure_workspace(db: DB, workspace_id: str) -> None:
    with db.global_session() as session:
        if session.get(Workspace, workspace_id) is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"workspace not found: {workspace_id}")


def plant_thread(
    db: DB,
    workspace_id: str,
    *,
    kind: str,
    content: str,
    chapter: str | None = None,
) -> PlotThread:
    """Create a planted thread in one workspace."""
    if kind not in VALID_KINDS:
        expected = ", ".join(VALID_KINDS)
        raise NovelError(
            ErrorCode.USAGE_ERROR, f"invalid kind: {kind} (expected one of: {expected})"
        )
    if not content.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "thread content must not be empty")
    if "".join(content.splitlines()) != content:
        raise NovelError(ErrorCode.USAGE_ERROR, "thread content must not contain newlines")
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        thread = PlotThread(
            workspace_id=workspace_id,
            content=content,
            kind=kind,
            status=STATUS_PLANTED,
            chapter=chapter or None,
        )
        session.add(thread)
        session.commit()
        return thread


def list_threads(db: DB, workspace_id: str) -> list[PlotThread]:
    """List every thread in one workspace, oldest first."""
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(PlotThread)
            .filter_by(workspace_id=workspace_id)
            .order_by(PlotThread.created_at, PlotThread.id)
            .all()
        )


def recover_thread(db: DB, workspace_id: str, thread_id: str) -> tuple[PlotThread, bool]:
    """Mark a thread recovered in one workspace; returns (thread, changed)."""
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        thread = (
            session.query(PlotThread)
            .filter_by(workspace_id=workspace_id, id=thread_id)
            .first()
        )
        if thread is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"plot thread not found: {thread_id}")
        if thread.status == STATUS_RECOVERED:
            return thread, False
        thread.status = STATUS_RECOVERED
        session.commit()
        return thread, True


def open_thread_lines(db: DB, workspace_id: str) -> list[str]:
    """Render planted/pending threads as `- [label] content（chapter）` lines."""
    lines: list[str] = []
    for thread in list_threads(db, workspace_id):
        if thread.status not in OPEN_STATUSES:
            continue
        label = KIND_LABELS.get(thread.kind, thread.kind)
        chapter = f"（{thread.chapter}）" if thread.chapter else ""
        lines.append(f"- [{label}] {thread.content}{chapter}")
    return lines


def plot_threads_section(db: DB, workspace_id: str) -> str:
    """Render the open-thread prompt section, or an empty string when there are none."""
    lines = open_thread_lines(db, workspace_id)
    if not lines:
        return ""
    return "悬置线索：\n" + "\n".join(lines)
