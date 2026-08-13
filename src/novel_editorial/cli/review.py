"""Review command group."""

from __future__ import annotations

import typer

from novel_editorial.core.config import load_settings
from novel_editorial.core.draft import find_draft_anywhere
from novel_editorial.core.review import add_review, list_reviews, resolve_reviewer
from novel_editorial.store.db import DB

review_app = typer.Typer(help="Review drafts")


@review_app.command("add")
def review_add(
    draft_id: str = typer.Argument(..., help="Draft id"),
    source: str = typer.Option("作者", "--from", help="Reviewer: 作者/总编/责编/写手/审稿"),
    content: str = typer.Option(..., "--content", help="Review comment"),
) -> None:
    """Add a review comment to a draft."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    draft = find_draft_anywhere(db, draft_id)
    role, actor = resolve_reviewer(db, draft.workspace_id, source)
    add_review(db, draft.workspace_id, draft_id, role=role, actor=actor, content=content)
    typer.echo(f"review added by {actor}: {content}")


@review_app.command("list")
def review_list(draft_id: str = typer.Argument(..., help="Draft id")) -> None:
    """List review comments for a draft."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    draft = find_draft_anywhere(db, draft_id)
    reviews = list_reviews(db, draft.workspace_id, draft_id)
    for review in reviews:
        typer.echo(f"[{review.role}] {review.actor}: {review.content}")
    if not reviews:
        typer.echo("no reviews yet")
