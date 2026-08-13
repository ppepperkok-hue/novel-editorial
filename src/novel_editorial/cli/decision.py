"""Decision command group."""

from __future__ import annotations

import typer

from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.config import load_settings
from novel_editorial.core.decision import decide
from novel_editorial.core.draft import find_draft_anywhere, list_pending_drafts
from novel_editorial.store.db import DB
from novel_editorial.store.models import Decision

decision_app = typer.Typer(help="Author decisions")


@decision_app.command("list")
def decision_list(draft_id: str = typer.Argument(..., help="Draft id")) -> None:
    """List decision records for a draft."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    draft = find_draft_anywhere(db, draft_id)
    with db.workspace_session(draft.workspace_id) as session:
        decisions = (
            session.query(Decision).filter_by(draft_id=draft_id).order_by(Decision.created_at).all()
        )
    for decision in decisions:
        suffix = f": {decision.content}" if decision.content else ""
        typer.echo(f"[{decision.action}] {decision.actor}{suffix}")
    if not decisions:
        typer.echo("no decisions yet")


@decision_app.command("pending")
def decision_pending(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """List drafts that passed the quality gate and await the author's decision."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    pending = list_pending_drafts(db, workspace_id)
    if not pending:
        typer.echo("no pending decisions")
        return
    for draft in pending:
        typer.echo(f"{draft.id}  {draft.title}  v{draft.current_version}  {draft.status}")


@decision_app.command("accept")
def decision_accept(draft_id: str = typer.Argument(..., help="Draft id")) -> None:
    """Accept a draft as the author."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    draft = find_draft_anywhere(db, draft_id)
    decide(db, draft.workspace_id, draft_id, action="accept")
    typer.echo(f"draft {draft_id} accepted")


@decision_app.command("reject")
def decision_reject(draft_id: str = typer.Argument(..., help="Draft id")) -> None:
    """Reject a draft as the author."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    draft = find_draft_anywhere(db, draft_id)
    decide(db, draft.workspace_id, draft_id, action="reject")
    typer.echo(f"draft {draft_id} rejected")


@decision_app.command("note")
def decision_note(
    draft_id: str = typer.Argument(..., help="Draft id"),
    content: str = typer.Option(..., "--content", help="Note text"),
) -> None:
    """Leave a note on a draft without changing its status."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    draft = find_draft_anywhere(db, draft_id)
    decide(db, draft.workspace_id, draft_id, action="note", content=content)
    typer.echo(f"note added to draft {draft_id}")
