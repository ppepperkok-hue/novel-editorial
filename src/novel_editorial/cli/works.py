"""Workspaces command group."""

from __future__ import annotations

import typer

from novel_editorial.cli.structure import (
    STATUS_LABELS,
    render_structure_lines,
    status_from_label,
)
from novel_editorial.core.archive import export_workspace_archive, import_workspace_archive
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.overview import build_overview
from novel_editorial.core.structure import set_workspace_status
from novel_editorial.core.workspace import create_workspace
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, Workspace

works_app = typer.Typer(help="Manage workspaces")


@works_app.command("create")
def works_create(
    title: str = typer.Argument(..., help="Work title"),
    genre: str = typer.Option("", "--genre", help="Genre"),
    description: str = typer.Option("", "--description", help="Short description"),
) -> None:
    """Create a workspace with a default editorial band."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    workspace = create_workspace(db, title=title, genre=genre, description=description)
    typer.echo(f"created workspace {workspace.id}: {title}")


@works_app.command("list")
def works_list() -> None:
    """List all workspaces."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    with db.global_session() as session:
        workspaces = session.query(Workspace).order_by(Workspace.created_at).all()
    for workspace in workspaces:
        typer.echo(f"{workspace.id}  {workspace.title}  {workspace.genre}")
    if not workspaces:
        typer.echo("no workspaces yet")


@works_app.command("overview")
def works_overview() -> None:
    """Show one aggregated glance across all workspaces."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    report = build_overview(db)
    if report.total == 0 and report.skipped == 0:
        typer.echo("no workspaces yet")
        return
    for item in report.overviews:
        genre_part = f"（{item.genre}）" if item.genre else ""
        status_label = STATUS_LABELS.get(item.status, item.status)
        timestamp = item.last_activity.isoformat(timespec="seconds")
        typer.echo(
            f"[{status_label}] {item.title}{genre_part}：待拍板 {item.pending_count}"
            f" · 进度 {item.structure} · 最近 {timestamp}"
        )


@works_app.command("show")
def works_show(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """Show a workspace and its editorial band."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    with db.global_session() as session:
        workspace = session.get(Workspace, workspace_id)
        if workspace is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"workspace not found: {workspace_id}")
        title = workspace.title
        genre = workspace.genre
        description = workspace.description
        status = workspace.status
    typer.echo(f"id: {workspace_id}")
    typer.echo(f"title: {title}")
    typer.echo(f"状态: {STATUS_LABELS.get(status, status)}")
    typer.echo(f"genre: {genre}")
    if description:
        typer.echo(f"description: {description}")
    with db.workspace_session(workspace_id) as session:
        agents = session.query(Agent).order_by(Agent.created_at).all()
    typer.echo("band:")
    for agent in agents:
        typer.echo(f"  {agent.role}: {agent.name}")
    structure_lines = render_structure_lines(db, workspace_id)
    if structure_lines:
        typer.echo("结构：")
        for line in structure_lines:
            typer.echo(line)


@works_app.command("status")
def works_status(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    status: str = typer.Argument(..., help="writing/completed/shelved（创作中/已完成/搁置）"),
) -> None:
    """Set a workspace's progress status."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    workspace = set_workspace_status(
        db, workspace_id, status_from_label(status)
    )
    typer.echo(f"status updated: {workspace.id} {workspace.status}")


@works_app.command("export")
def works_export(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    target: str = typer.Argument(..., help="Target archive path or directory"),
) -> None:
    """Export one workspace to a verifiable ZIP archive."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    path = export_workspace_archive(db, workspace_id, target)
    typer.echo(f"exported: {path}")


@works_app.command("import")
def works_import(archive_path: str = typer.Argument(..., help="Archive path")) -> None:
    """Import one workspace archive as a brand-new workspace."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    workspace = import_workspace_archive(db, archive_path)
    typer.echo(f"imported workspace {workspace.id}: {workspace.title}")
