"""Style command group."""

from __future__ import annotations

import typer

from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.config import load_settings
from novel_editorial.core.style import get_style_anchor, set_style_anchor
from novel_editorial.store.db import DB

style_app = typer.Typer(help="Manage style anchors")


@style_app.command("set")
def style_set(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    description: str = typer.Option("", "--description", help="Style description"),
    forbidden: str = typer.Option("", "--forbidden", help="Forbidden words, comma separated"),
) -> None:
    """Set the workspace style anchor."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    set_style_anchor(db, workspace_id, description=description, forbidden_words=forbidden)
    typer.echo(f"style anchor updated: {workspace_id}")


@style_app.command("show")
def style_show(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """Show the workspace style anchor."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    anchor = get_style_anchor(db, workspace_id)
    typer.echo(f"description: {anchor.description or '(empty)'}")
    typer.echo(f"forbidden: {anchor.forbidden_words or '(empty)'}")
