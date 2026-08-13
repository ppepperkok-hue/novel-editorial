"""Draft command group."""

from __future__ import annotations

import typer

from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.config import load_settings
from novel_editorial.core.draft import (
    diff_versions,
    find_draft_anywhere,
    generate_draft,
    get_draft_version,
    list_drafts,
    revise_draft,
)
from novel_editorial.llm.client import build_client
from novel_editorial.store.db import DB

draft_app = typer.Typer(help="Manage drafts")


@draft_app.command("generate")
def draft_generate(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    title: str = typer.Option("未命名章节", "--title", help="Chapter title"),
) -> None:
    """Generate a draft version (writer + memory pack + LLM)."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    client = build_client(settings)
    draft = generate_draft(
        db,
        workspace_id,
        title=title,
        client=client,
        quality_threshold=settings.quality_threshold,
    )
    typer.echo(f"draft {draft.id} {draft.title} now at v{draft.current_version}")
    if draft.status == "draft":
        typer.echo(f"awaiting decision: {draft.id}")


@draft_app.command("revise")
def draft_revise(
    draft_id: str = typer.Argument(..., help="Draft id"),
    reason: str = typer.Option("revision", "--reason", help="Reason for the revision"),
) -> None:
    """Re-generate a draft as a new version (writer + LLM)."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    draft = find_draft_anywhere(db, draft_id)
    client = build_client(settings)
    revised = revise_draft(
        db,
        draft.workspace_id,
        draft_id,
        reason=reason,
        client=client,
        quality_threshold=settings.quality_threshold,
    )
    typer.echo(f"draft {revised.id} {revised.title} now at v{revised.current_version}")
    if revised.status == "draft":
        typer.echo(f"awaiting decision: {revised.id}")


@draft_app.command("list")
def draft_list(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """List drafts in a workspace."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    for draft in list_drafts(db, workspace_id):
        typer.echo(f"{draft.id}  {draft.title}  v{draft.current_version}  {draft.status}")


@draft_app.command("show")
def draft_show(draft_id: str = typer.Argument(..., help="Draft id")) -> None:
    """Show a draft with its latest version content."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    draft = find_draft_anywhere(db, draft_id)
    version = get_draft_version(db, draft.workspace_id, draft_id, draft.current_version)
    typer.echo(f"{draft.title} (v{draft.current_version}, {draft.status})")
    typer.echo(f"reason: {version.reason}")
    typer.echo("---")
    typer.echo(version.content)


@draft_app.command("diff")
def draft_diff(
    draft_id: str = typer.Argument(..., help="Draft id"),
    version_a: int = typer.Argument(..., help="Version A"),
    version_b: int = typer.Argument(..., help="Version B"),
) -> None:
    """Show the diff between two versions of a draft."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    draft = find_draft_anywhere(db, draft_id)
    first = get_draft_version(db, draft.workspace_id, draft_id, version_a)
    second = get_draft_version(db, draft.workspace_id, draft_id, version_b)
    output = diff_versions(first, second)
    typer.echo(output if output else "no differences")
