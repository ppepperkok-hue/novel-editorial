"""Inspiration command group (N15)."""

from __future__ import annotations

import typer

from novel_editorial.core.config import load_settings
from novel_editorial.core.inspiration import (
    add_inspiration,
    get_inspiration,
    list_inspirations,
    remove_inspiration,
)
from novel_editorial.store.db import DB

inspiration_app = typer.Typer(help="Manage lightweight inspiration material")


@inspiration_app.command("add")
def inspiration_add(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    content: str = typer.Option(..., "--content", help="Inspiration content"),
    kind: str = typer.Option(
        "灵感", "--kind", help="Open kind label (default: 灵感)"
    ),
    source: str = typer.Option("", "--source", help="Source of the inspiration"),
) -> None:
    """Add one inspiration snippet."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    inspiration = add_inspiration(
        db,
        workspace_id,
        content=content,
        kind=kind,
        source=source,
    )
    typer.echo(f"added {inspiration.id} [{inspiration.kind}] {inspiration.content}")


@inspiration_app.command("list")
def inspiration_list(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    kind: str | None = typer.Option(
        None, "--kind", help="Filter by exact kind label"
    ),
    keyword: str | None = typer.Option(
        None, "--keyword", help="Match content/source (case-insensitive substring)"
    ),
) -> None:
    """List inspirations, newest first."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    rows = list_inspirations(db, workspace_id, kind=kind, keyword=keyword)
    if not rows:
        typer.echo("no inspirations")
        return
    for row in rows:
        typer.echo(f"{row.id} [{row.kind}] {row.content}")


@inspiration_app.command("show")
def inspiration_show(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    inspiration_id: str = typer.Argument(..., help="Inspiration id"),
) -> None:
    """Show one inspiration with its source."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    inspiration = get_inspiration(db, workspace_id, inspiration_id)
    typer.echo(f"kind: {inspiration.kind}")
    typer.echo(f"content: {inspiration.content}")
    typer.echo(f"source: {inspiration.source or '(empty)'}")


@inspiration_app.command("remove")
def inspiration_remove(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    inspiration_id: str = typer.Argument(..., help="Inspiration id"),
) -> None:
    """Remove one inspiration."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    inspiration = remove_inspiration(db, workspace_id, inspiration_id)
    typer.echo(f"removed {inspiration.id} [{inspiration.kind}]")
