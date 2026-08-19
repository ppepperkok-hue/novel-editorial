"""Structure command group: optional volume/chapter/section tree of a work."""

from __future__ import annotations

import typer

from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.structure import (
    KIND_CHAPTER,
    KIND_SECTION,
    KIND_VOLUME,
    STATUS_COMPLETED,
    STATUS_SHELVED,
    STATUS_WRITING,
    create_node,
    list_structure,
    move_node,
    remove_node,
    rename_node,
    set_node_status,
)
from novel_editorial.store.db import DB
from novel_editorial.store.models import Draft

structure_app = typer.Typer(help="Manage the optional structure tree of a work")

KIND_LABELS: dict[str, str] = {
    KIND_VOLUME: "卷",
    KIND_CHAPTER: "章",
    KIND_SECTION: "篇目",
}
STATUS_LABELS: dict[str, str] = {
    STATUS_WRITING: "创作中",
    STATUS_COMPLETED: "已完成",
    STATUS_SHELVED: "搁置",
}


def kind_from_label(kind: str) -> str:
    """Map a kind input (canonical or Chinese label) to its canonical value."""
    for canonical, label in KIND_LABELS.items():
        if kind == canonical or kind == label:
            return canonical
    expected = "、".join(KIND_LABELS.values())
    raise NovelError(
        ErrorCode.USAGE_ERROR, f"invalid kind: {kind} (expected one of: {expected})"
    )


def status_from_label(status: str) -> str:
    """Map a status input (canonical or Chinese label) to its canonical value."""
    for canonical, label in STATUS_LABELS.items():
        if status == canonical or status == label:
            return canonical
    expected = "、".join(STATUS_LABELS.values())
    raise NovelError(
        ErrorCode.USAGE_ERROR,
        f"invalid status: {status} (expected one of: {expected})",
    )


def _draft_titles(db: DB, workspace_id: str) -> dict[str, str]:
    """Map every draft id in the workspace to its title."""
    with db.workspace_session(workspace_id) as session:
        drafts = session.query(Draft).filter_by(workspace_id=workspace_id).all()
    return {draft.id: draft.title for draft in drafts}


def render_structure_lines(db: DB, workspace_id: str) -> list[str]:
    """Render the structure tree as display lines shared by list/show commands."""
    nodes = list_structure(db, workspace_id)
    if not nodes:
        return []
    draft_titles = _draft_titles(db, workspace_id)
    depth: dict[str, int] = {}
    lines: list[str] = []
    for node in nodes:
        node_depth = (
            0 if node.parent_id is None else depth.get(node.parent_id, 0) + 1
        )
        depth[node.id] = node_depth
        label = KIND_LABELS.get(node.kind, node.kind)
        marker = ""
        if node.status == STATUS_COMPLETED:
            marker = " [已完成]"
        elif node.status == STATUS_SHELVED:
            marker = " [搁置]"
        draft_title = draft_titles.get(node.draft_id) if node.draft_id else None
        line = f"{'  ' * node_depth}[{label}] {node.title}（{node.id}）{marker}"
        if draft_title:
            line += f" {draft_title}"
        lines.append(line)
    return lines


@structure_app.command("add")
def structure_add(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    kind: str = typer.Argument(..., help="Node kind: volume/chapter/section（卷/章/篇目）"),
    title: str = typer.Argument(..., help="Node title"),
    parent: str | None = typer.Option(None, "--parent", help="Parent node id"),
    draft: str | None = typer.Option(None, "--draft", help="Draft id to attach"),
    order: int | None = typer.Option(None, "--order", help="Sort order among siblings"),
) -> None:
    """Add a structure node (volume / chapter / section)."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    node = create_node(
        db,
        workspace_id,
        kind=kind_from_label(kind),
        title=title,
        parent_id=parent,
        draft_id=draft,
        sort_order=order,
    )
    typer.echo(f"created {node.id} {node.kind} {node.title}")


@structure_app.command("list")
def structure_list(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """Show the structure tree with status markers and attached draft titles."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    lines = render_structure_lines(db, workspace_id)
    if not lines:
        typer.echo("no structure")
        return
    for line in lines:
        typer.echo(line)


@structure_app.command("rename")
def structure_rename(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    node_id: str = typer.Argument(..., help="Node id"),
    title: str = typer.Argument(..., help="New node title"),
) -> None:
    """Rename one structure node."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    node = rename_node(db, workspace_id, node_id, title)
    typer.echo(f"renamed {node.id}")


@structure_app.command("move")
def structure_move(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    node_id: str = typer.Argument(..., help="Node id"),
    parent: str | None = typer.Option(None, "--parent", help="New parent node id"),
    root: bool = typer.Option(False, "--root", help="Move to the root level"),
    order: int | None = typer.Option(None, "--order", help="New sort order"),
) -> None:
    """Move a node under a parent or back to the root level."""
    if parent is not None and root:
        raise NovelError(
            ErrorCode.USAGE_ERROR, "--parent and --root are mutually exclusive"
        )
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    parent_id = None if root or parent is None else parent
    node = move_node(db, workspace_id, node_id, parent_id=parent_id, sort_order=order)
    typer.echo(f"moved {node.id}")


@structure_app.command("remove")
def structure_remove(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    node_id: str = typer.Argument(..., help="Node id"),
) -> None:
    """Remove a node and its whole subtree (draft bodies are kept)."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    removed = remove_node(db, workspace_id, node_id)
    typer.echo(f"removed {removed} node(s)")


@structure_app.command("status")
def structure_status(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    node_id: str = typer.Argument(..., help="Node id"),
    status: str = typer.Argument(..., help="writing/completed/shelved（创作中/已完成/搁置）"),
) -> None:
    """Set a node's progress status."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    node = set_node_status(db, workspace_id, node_id, status_from_label(status))
    typer.echo(f"status updated: {node.id} {node.status}")
