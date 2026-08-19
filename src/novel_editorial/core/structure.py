"""Workspace structure tree services (N13 J1): volumes, chapters, sections.

The structure is an optional organization view on top of a workspace's flat
drafts: nodes are pure metadata, never own content, and deleting a node never
touches any draft body. Progress status (writing / completed / shelved) is a
trackable marker only and blocks no creation commands.
"""

from __future__ import annotations

import sys

from sqlalchemy.orm import Session

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.events import EventType
from novel_editorial.store.db import DB
from novel_editorial.store.events import record_event
from novel_editorial.store.models import Workspace, WorkspaceStructureNode

KIND_VOLUME = "volume"
KIND_CHAPTER = "chapter"
KIND_SECTION = "section"
VALID_KINDS: tuple[str, ...] = (KIND_VOLUME, KIND_CHAPTER, KIND_SECTION)

STATUS_WRITING = "writing"
STATUS_COMPLETED = "completed"
STATUS_SHELVED = "shelved"
VALID_STATUSES: tuple[str, ...] = (
    STATUS_WRITING,
    STATUS_COMPLETED,
    STATUS_SHELVED,
)

# Only kind -> allowed parent kind; None means the node must be a root.
_PARENT_KINDS: dict[str, str | None] = {
    KIND_VOLUME: None,
    KIND_CHAPTER: KIND_VOLUME,
    KIND_SECTION: KIND_CHAPTER,
}


def _ensure_workspace(db: DB, workspace_id: str) -> None:
    """Raise NOT_FOUND when the workspace is not registered."""
    with db.global_session() as session:
        if session.get(Workspace, workspace_id) is None:
            raise NovelError(
                ErrorCode.NOT_FOUND, f"workspace not found: {workspace_id}"
            )


def _validate_kind(kind: str) -> None:
    """Raise USAGE_ERROR unless kind is one of the supported node kinds."""
    if kind not in VALID_KINDS:
        expected = ", ".join(VALID_KINDS)
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"invalid kind: {kind} (expected one of: {expected})",
        )


def _validate_status(status: str) -> None:
    """Raise USAGE_ERROR unless status is one of the supported progress states."""
    if status not in VALID_STATUSES:
        expected = ", ".join(VALID_STATUSES)
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"invalid status: {status} (expected one of: {expected})",
        )


def _validate_sort_order(sort_order: int | None) -> None:
    """Raise USAGE_ERROR unless sort_order is non-negative."""
    if sort_order is not None and sort_order < 0:
        raise NovelError(
            ErrorCode.USAGE_ERROR, f"invalid sort order: {sort_order}"
        )


def _validate_parent(kind: str, parent: WorkspaceStructureNode | None) -> None:
    """Raise USAGE_ERROR when the parent kind is not a valid parent for kind."""
    if parent is None:
        return
    expected = _PARENT_KINDS[kind]
    if expected is None:
        raise NovelError(
            ErrorCode.USAGE_ERROR, f"{kind} node cannot have a parent"
        )
    if parent.kind != expected:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"invalid parent kind: {parent.kind} (expected {expected})",
        )


def _next_sort_order(
    session: Session, workspace_id: str, parent_id: str | None
) -> int:
    """Return the next sort order (current sibling max + 1) for a parent."""
    rows = (
        session.query(WorkspaceStructureNode.sort_order)
        .filter_by(workspace_id=workspace_id, parent_id=parent_id)
        .all()
    )
    max_order = max((row[0] for row in rows), default=0)
    return max_order + 1


def _subtree_ids(
    session: Session, workspace_id: str, root_id: str
) -> set[str]:
    """Return root_id plus every descendant id inside the workspace."""
    nodes = (
        session.query(WorkspaceStructureNode)
        .filter_by(workspace_id=workspace_id)
        .all()
    )
    children: dict[str, list[str]] = {}
    for node in nodes:
        if node.parent_id is not None:
            children.setdefault(node.parent_id, []).append(node.id)
    ids: set[str] = set()
    stack = [root_id]
    while stack:
        current = stack.pop()
        if current in ids:
            continue
        ids.add(current)
        stack.extend(children.get(current, []))
    return ids


def _record_event_safe(
    db: DB, workspace_id: str, *, kind: str, payload: dict
) -> None:
    """Persist a SYSTEM event; a failure only warns and never rolls back."""
    try:
        record_event(
            db,
            workspace_id,
            type=EventType.SYSTEM,
            actor="system",
            payload={"kind": kind, **payload},
        )
    except Exception as exc:  # noqa: BLE001 - event recording is best-effort
        print(f"warning: {kind} event skipped: {exc}", file=sys.stderr)


def create_node(
    db: DB,
    workspace_id: str,
    *,
    kind: str,
    title: str,
    parent_id: str | None = None,
    draft_id: str | None = None,
    sort_order: int | None = None,
) -> WorkspaceStructureNode:
    """Create one structure node under an optional, valid parent."""
    _validate_kind(kind)
    if not title.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "node title must not be empty")
    _validate_sort_order(sort_order)
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        parent = None
        if parent_id is not None:
            parent = (
                session.query(WorkspaceStructureNode)
                .filter_by(workspace_id=workspace_id, id=parent_id)
                .first()
            )
            if parent is None:
                raise NovelError(
                    ErrorCode.NOT_FOUND,
                    f"structure node not found: {parent_id}",
                )
        _validate_parent(kind, parent)
        order = (
            sort_order
            if sort_order is not None
            else _next_sort_order(session, workspace_id, parent_id)
        )
        node = WorkspaceStructureNode(
            workspace_id=workspace_id,
            parent_id=parent_id,
            kind=kind,
            title=title,
            sort_order=order,
            draft_id=draft_id,
        )
        session.add(node)
        session.commit()
        node_id = node.id
    _record_event_safe(
        db,
        workspace_id,
        kind="structure_created",
        payload={
            "node_id": node_id,
            "title": title,
            "parent_id": parent_id,
        },
    )
    return node


def list_structure(db: DB, workspace_id: str) -> list[WorkspaceStructureNode]:
    """Return every node as a flat parent-first list, deterministic ordering."""
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        nodes = (
            session.query(WorkspaceStructureNode)
            .filter_by(workspace_id=workspace_id)
            .all()
        )
    nodes.sort(key=lambda node: (node.sort_order, node.created_at, node.id))
    by_parent: dict[str | None, list[WorkspaceStructureNode]] = {}
    for node in nodes:
        by_parent.setdefault(node.parent_id, []).append(node)
    ordered: list[WorkspaceStructureNode] = []

    def visit(parent_id: str | None) -> None:
        for child in by_parent.get(parent_id, []):
            ordered.append(child)
            visit(child.id)

    visit(None)
    if len(ordered) < len(nodes):
        known = {node.id for node in ordered}
        for node in nodes:
            if node.id not in known:
                ordered.append(node)
    return ordered


def rename_node(
    db: DB, workspace_id: str, node_id: str, title: str
) -> WorkspaceStructureNode:
    """Rename one structure node inside a workspace."""
    if not title.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "node title must not be empty")
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        node = (
            session.query(WorkspaceStructureNode)
            .filter_by(workspace_id=workspace_id, id=node_id)
            .first()
        )
        if node is None:
            raise NovelError(
                ErrorCode.NOT_FOUND, f"structure node not found: {node_id}"
            )
        old_title = node.title
        node.title = title
        session.commit()
    _record_event_safe(
        db,
        workspace_id,
        kind="structure_renamed",
        payload={"node_id": node_id, "title": title, "old_title": old_title},
    )
    return node


def move_node(
    db: DB,
    workspace_id: str,
    node_id: str,
    parent_id: str | None = None,
    sort_order: int | None = None,
) -> WorkspaceStructureNode:
    """Move one node to a new parent (None = root), guarding cycles and levels."""
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        node = (
            session.query(WorkspaceStructureNode)
            .filter_by(workspace_id=workspace_id, id=node_id)
            .first()
        )
        if node is None:
            raise NovelError(
                ErrorCode.NOT_FOUND, f"structure node not found: {node_id}"
            )
        _validate_sort_order(sort_order)
        parent = None
        if parent_id is not None:
            parent = (
                session.query(WorkspaceStructureNode)
                .filter_by(workspace_id=workspace_id, id=parent_id)
                .first()
            )
            if parent is None:
                raise NovelError(
                    ErrorCode.NOT_FOUND,
                    f"structure node not found: {parent_id}",
                )
        if parent_id is not None and parent_id in _subtree_ids(
            session, workspace_id, node_id
        ):
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                "cannot move a node into itself or its own subtree",
            )
        _validate_parent(node.kind, parent)
        if parent_id == node.parent_id and sort_order is None:
            return node
        next_order = (
            sort_order
            if sort_order is not None
            else _next_sort_order(session, workspace_id, parent_id)
        )
        node.parent_id = parent_id
        node.sort_order = next_order
        session.commit()
        moved_order = node.sort_order
    _record_event_safe(
        db,
        workspace_id,
        kind="structure_moved",
        payload={
            "node_id": node_id,
            "parent_id": parent_id,
            "sort_order": moved_order,
        },
    )
    return node


def remove_node(db: DB, workspace_id: str, node_id: str) -> int:
    """Remove one node and its whole subtree; draft bodies are never touched."""
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        node = (
            session.query(WorkspaceStructureNode)
            .filter_by(workspace_id=workspace_id, id=node_id)
            .first()
        )
        if node is None:
            raise NovelError(
                ErrorCode.NOT_FOUND, f"structure node not found: {node_id}"
            )
        ids = _subtree_ids(session, workspace_id, node_id)
        session.query(WorkspaceStructureNode).filter(
            WorkspaceStructureNode.id.in_(ids)
        ).delete(synchronize_session=False)
        session.commit()
        removed = len(ids)
    _record_event_safe(
        db,
        workspace_id,
        kind="structure_removed",
        payload={"node_id": node_id, "removed_count": removed},
    )
    return removed


def set_node_status(
    db: DB, workspace_id: str, node_id: str, status: str
) -> WorkspaceStructureNode:
    """Set a node's progress status (writing / completed / shelved)."""
    _validate_status(status)
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        node = (
            session.query(WorkspaceStructureNode)
            .filter_by(workspace_id=workspace_id, id=node_id)
            .first()
        )
        if node is None:
            raise NovelError(
                ErrorCode.NOT_FOUND, f"structure node not found: {node_id}"
            )
        old_status = node.status
        node.status = status
        session.commit()
    _record_event_safe(
        db,
        workspace_id,
        kind="structure_status_changed",
        payload={"node_id": node_id, "status": status, "old_status": old_status},
    )
    return node


def set_workspace_status(db: DB, workspace_id: str, status: str) -> Workspace:
    """Set a workspace's progress status (writing / completed / shelved)."""
    _validate_status(status)
    _ensure_workspace(db, workspace_id)
    with db.global_session() as session:
        workspace = session.get(Workspace, workspace_id)
        if workspace is None:
            raise NovelError(
                ErrorCode.NOT_FOUND, f"workspace not found: {workspace_id}"
            )
        old_status = workspace.status
        workspace.status = status
        session.commit()
    _record_event_safe(
        db,
        workspace_id,
        kind="workspace_status_changed",
        payload={"status": status, "old_status": old_status},
    )
    return workspace


def count_structure(db: DB, workspace_id: str) -> dict[str, int]:
    """Count nodes by kind and completed chapters for one workspace."""
    _ensure_workspace(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        nodes = (
            session.query(WorkspaceStructureNode)
            .filter_by(workspace_id=workspace_id)
            .all()
        )
    volumes = sum(1 for node in nodes if node.kind == KIND_VOLUME)
    chapters = sum(1 for node in nodes if node.kind == KIND_CHAPTER)
    sections = sum(1 for node in nodes if node.kind == KIND_SECTION)
    completed_chapters = sum(
        1
        for node in nodes
        if node.kind == KIND_CHAPTER and node.status == STATUS_COMPLETED
    )
    return {
        "volumes": volumes,
        "chapters": chapters,
        "sections": sections,
        "completed_chapters": completed_chapters,
        "total_nodes": len(nodes),
    }
