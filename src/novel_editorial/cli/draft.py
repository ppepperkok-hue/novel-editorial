"""Draft command group."""

from __future__ import annotations

import typer

from novel_editorial.core import proactive
from novel_editorial.core.agents import get_agent_by_id, get_default_writer, resolve_agent
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
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.review import list_reviews
from novel_editorial.llm.client import build_client
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, AgentRole, Draft

draft_app = typer.Typer(help="Manage drafts")


def _content_excerpt(content: str, limit: int = 20) -> str:
    """Flatten the opening of draft content into one short, assertable line."""
    return " ".join(content.split())[:limit]


def _resolve_writer_option(
    db: DB, workspace_id: str, writer: str | None
) -> Agent | None:
    """Resolve the --writer option, or None when the default writer is wanted."""
    if writer is None:
        return None
    agent = resolve_agent(db, workspace_id, writer)
    if agent.role != AgentRole.WRITER:
        raise NovelError(
            ErrorCode.USAGE_ERROR, f"{agent.name} is not a writer"
        )
    return agent


def _writer_name(db: DB, workspace_id: str, draft: Draft) -> str:
    """Return the draft writer's name, falling back to the default writer."""
    if draft.writer_id is not None:
        agent = get_agent_by_id(db, workspace_id, draft.writer_id)
        if agent is not None:
            return agent.name
    return get_default_writer(db, workspace_id).name


def _revision_is_rebuttal(db: DB, workspace_id: str, draft_id: str) -> bool:
    """True when the revision round already emits the writer rebuttal message."""
    return any(review.role == "agent" for review in list_reviews(db, workspace_id, draft_id))


def _record_proactive(db: DB, workspace_id: str, trigger: str, context: dict) -> None:
    """Evaluate and echo proactive messages; a failure never rolls business back."""
    try:
        messages = proactive.record_proactive_messages(db, workspace_id, trigger, context)
    except Exception as exc:
        typer.echo(f"warning: proactive messages skipped: {exc}", err=True)
        return
    for message in messages:
        typer.echo(f"{message.actor}: {message.content}")


@draft_app.command("generate")
def draft_generate(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    title: str = typer.Option("未命名章节", "--title", help="Chapter title"),
    writer: str | None = typer.Option(
        None, "--writer", help="Writer name or id (default: first writer)"
    ),
) -> None:
    """Generate a draft version (writer + memory pack + LLM)."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    client = build_client(settings)
    writer_agent = _resolve_writer_option(db, workspace_id, writer)
    draft = generate_draft(
        db,
        workspace_id,
        title=title,
        client=client,
        quality_threshold=settings.quality_threshold,
        writer=writer_agent,
    )
    typer.echo(f"draft {draft.id} {draft.title} now at v{draft.current_version}")
    if draft.status == "draft":
        typer.echo(f"awaiting decision: {draft.id}")
    version = get_draft_version(db, workspace_id, draft.id, draft.current_version)
    context = {
        "title": draft.title,
        "excerpt": _content_excerpt(version.content),
        "passed": draft.status == "draft",
        "current_version": draft.current_version,
        "reason": version.reason,
    }
    _record_proactive(db, workspace_id, proactive.TRIGGER_DRAFT_GENERATED, context)
    if draft.status == "draft":
        _record_proactive(db, workspace_id, proactive.TRIGGER_DRAFT_GATE_PASSED, context)


@draft_app.command("revise")
def draft_revise(
    draft_id: str = typer.Argument(..., help="Draft id"),
    reason: str = typer.Option("revision", "--reason", help="Reason for the revision"),
    writer: str | None = typer.Option(
        None, "--writer", help="Writer name or id (default: original writer)"
    ),
) -> None:
    """Re-generate a draft as a new version (writer + LLM)."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    draft = find_draft_anywhere(db, draft_id)
    client = build_client(settings)
    writer_agent = _resolve_writer_option(db, draft.workspace_id, writer)
    revised = revise_draft(
        db,
        draft.workspace_id,
        draft_id,
        reason=reason,
        client=client,
        quality_threshold=settings.quality_threshold,
        writer=writer_agent,
    )
    typer.echo(f"draft {revised.id} {revised.title} now at v{revised.current_version}")
    if revised.status == "draft":
        typer.echo(f"awaiting decision: {revised.id}")
    _record_proactive(
        db,
        draft.workspace_id,
        proactive.TRIGGER_DRAFT_REVISED,
        {
            "rebutted": _revision_is_rebuttal(db, draft.workspace_id, draft_id),
            "passed": revised.status == "draft",
        },
    )


@draft_app.command("list")
def draft_list(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """List drafts in a workspace."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    for draft in list_drafts(db, workspace_id):
        writer_name = _writer_name(db, workspace_id, draft)
        typer.echo(
            f"{draft.id}  {draft.title}  v{draft.current_version}  "
            f"{draft.status}  （{writer_name}）"
        )


@draft_app.command("show")
def draft_show(draft_id: str = typer.Argument(..., help="Draft id")) -> None:
    """Show a draft with its latest version content."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    draft = find_draft_anywhere(db, draft_id)
    version = get_draft_version(db, draft.workspace_id, draft_id, draft.current_version)
    typer.echo(f"{draft.title} (v{draft.current_version}, {draft.status})")
    typer.echo(f"writer: {_writer_name(db, draft.workspace_id, draft)}")
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
