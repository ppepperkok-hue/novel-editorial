"""Workspaces command group."""

from __future__ import annotations

import typer

from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
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
    typer.echo(f"id: {workspace_id}")
    typer.echo(f"title: {title}")
    typer.echo(f"genre: {genre}")
    if description:
        typer.echo(f"description: {description}")
    with db.workspace_session(workspace_id) as session:
        agents = session.query(Agent).order_by(Agent.created_at).all()
    typer.echo("band:")
    for agent in agents:
        typer.echo(f"  {agent.role}: {agent.name}")
