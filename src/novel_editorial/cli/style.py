"""Style command group."""

from __future__ import annotations

import typer

from novel_editorial.core import proactive
from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.config import load_settings
from novel_editorial.core.style import get_style_anchor, set_style_anchor
from novel_editorial.store.db import DB

style_app = typer.Typer(help="Manage style anchors")


def _record_proactive(db: DB, workspace_id: str, trigger: str, context: dict) -> None:
    """Evaluate and echo proactive messages; a failure never rolls business back."""
    try:
        messages = proactive.record_proactive_messages(db, workspace_id, trigger, context)
    except Exception as exc:
        typer.echo(f"warning: proactive messages skipped: {exc}", err=True)
        return
    for message in messages:
        typer.echo(f"{message.actor}: {message.content}")


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
    anchor = set_style_anchor(db, workspace_id, description=description, forbidden_words=forbidden)
    typer.echo(f"style anchor updated: {workspace_id}")
    _record_proactive(
        db,
        workspace_id,
        proactive.TRIGGER_STYLE_SET,
        {"description": anchor.description, "forbidden_words": anchor.forbidden_words},
    )


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
