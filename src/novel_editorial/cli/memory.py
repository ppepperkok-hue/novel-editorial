"""Memory command group."""

from __future__ import annotations

import typer

from novel_editorial.core.agents import resolve_agent
from novel_editorial.core.chat import AUTHOR_ACTOR, get_workspace_or_raise
from novel_editorial.core.config import load_settings
from novel_editorial.core.draft import build_memory_pack
from novel_editorial.core.memory import add_memory_note, delete_memory_note, list_memory_notes
from novel_editorial.core.views import build_role_view, search_memory
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent

memory_app = typer.Typer(help="Inspect writing memory")


@memory_app.command("pack")
def memory_pack(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """Show the writing memory pack for a workspace."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    typer.echo(build_memory_pack(db, workspace_id))


@memory_app.command("view")
def memory_view(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    as_role: str = typer.Option(
        "写手",
        "--as",
        help="View role: 写手/主编/总编/责编/作者 (default: 写手)",
    ),
) -> None:
    """Show the default layered view for one role."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    typer.echo(build_role_view(db, workspace_id, as_role))


@memory_app.command("search")
def memory_search(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    keyword: str = typer.Argument(..., help="Search keyword"),
) -> None:
    """Search archive, messages, reviews, versions, and notes with source citations."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    typer.echo(search_memory(db, workspace_id, keyword))


def _agent_names(db: DB, workspace_id: str) -> dict[str, str]:
    with db.workspace_session(workspace_id) as session:
        agents = session.query(Agent).filter_by(workspace_id=workspace_id).all()
    return {agent.id: agent.name for agent in agents}


@memory_app.command("note")
def memory_note(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    target: str = typer.Argument(..., help="Agent id or role alias (总编/责编/写手/审稿)"),
    content: str = typer.Option(..., "--content", help="Private note content"),
    actor: str = typer.Option(
        AUTHOR_ACTOR,
        "--as",
        help="Note author: 总编/主编/责编/写手/审稿 (作者只读，需以伙伴身份写入)",
    ),
) -> None:
    """Write a partner's private note; the author is read-only."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    agent = resolve_agent(db, workspace_id, target)
    add_memory_note(db, workspace_id, agent.id, actor=actor, content=content)
    typer.echo(f"note added to {agent.name} by {actor}")


@memory_app.command("notes")
def memory_notes(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    target: str | None = typer.Argument(None, help="Agent id or role alias (omit for all)"),
) -> None:
    """List private notes with their ids; omit the agent to see every partner's notes."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    agent_id: str | None = None
    agent_name: str | None = None
    if target is not None:
        agent = resolve_agent(db, workspace_id, target)
        agent_id = agent.id
        agent_name = agent.name
    notes = list_memory_notes(db, workspace_id, agent_id=agent_id)
    if not notes:
        if agent_name is not None:
            typer.echo(f"no notes for {agent_name}")
        else:
            typer.echo("no memory notes yet")
        return
    names = _agent_names(db, workspace_id)
    for note in notes:
        owner = names.get(note.agent_id, note.agent_id)
        typer.echo(f"{note.id} [{owner}] {note.content}")


@memory_app.command("delete")
def memory_delete(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    memory_id: str = typer.Argument(..., help="Memory note id"),
) -> None:
    """Delete one private note."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    delete_memory_note(db, workspace_id, memory_id)
    typer.echo(f"note deleted: {memory_id}")
