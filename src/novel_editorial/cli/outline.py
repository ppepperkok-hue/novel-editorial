"""Outline command group: versioned creation plan of a work."""

from __future__ import annotations

import typer

from novel_editorial.core.config import load_settings
from novel_editorial.core.outline import (
    create_outline,
    get_outline,
    list_outline_versions,
    revise_outline,
)
from novel_editorial.store.db import DB

outline_app = typer.Typer(help="Manage the versioned outline plan of a work")

REASON_DISPLAY_LIMIT = 40


@outline_app.command("create")
def outline_create(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    content: str = typer.Option(..., "--content", help="Outline content"),
    actor: str = typer.Option("作者", "--actor", help="Outline author"),
) -> None:
    """Create the first outline version."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    outline = create_outline(db, workspace_id, content=content, actor=actor)
    typer.echo(f"outline v{outline.version} created")


@outline_app.command("revise")
def outline_revise(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    content: str = typer.Option(..., "--content", help="New outline content"),
    reason: str = typer.Option(..., "--reason", help="Reason for the revision"),
    actor: str = typer.Option("作者", "--actor", help="Actor making the revision"),
) -> None:
    """Revise the current outline: bump the version and record the change."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    outline = revise_outline(
        db,
        workspace_id,
        content=content,
        reason=reason,
        actor=actor,
    )
    typer.echo(f"outline v{outline.version} saved")


@outline_app.command("show")
def outline_show(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """Show the current outline version."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    outline = get_outline(db, workspace_id)
    if outline is None:
        typer.echo("no outline")
        return
    typer.echo(f"outline v{outline.version}：")
    typer.echo(outline.content)


@outline_app.command("history")
def outline_history(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    limit: int = typer.Option(20, "--limit", min=1, help="Max versions to show"),
) -> None:
    """Show outline versions, newest first."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    versions = list_outline_versions(db, workspace_id, limit=limit)
    if not versions:
        typer.echo("no outline")
        return
    for version in versions:
        reason = version.reason
        if len(reason) > REASON_DISPLAY_LIMIT:
            reason = reason[:REASON_DISPLAY_LIMIT] + "…"
        when = version.created_at.isoformat(timespec="seconds")
        typer.echo(f"v{version.version} {when} {version.actor} {reason}")
