"""Plot command group."""

from __future__ import annotations

import typer

from novel_editorial.core import proactive
from novel_editorial.core.config import load_settings
from novel_editorial.core.plot import KIND_LABELS, list_threads, plant_thread, recover_thread
from novel_editorial.store.db import DB

plot_app = typer.Typer(help="Track narrative plot threads")


def _record_proactive(db: DB, workspace_id: str, trigger: str, context: dict) -> None:
    """Evaluate and echo proactive messages; a failure never rolls business back."""
    try:
        messages = proactive.record_proactive_messages(db, workspace_id, trigger, context)
    except Exception as exc:
        typer.echo(f"warning: proactive messages skipped: {exc}", err=True)
        return
    for message in messages:
        typer.echo(f"{message.actor}: {message.content}")


@plot_app.command("plant")
def plot_plant(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    kind: str = typer.Option(..., "--kind", help="Thread kind: foreshadow/goal/hook"),
    content: str = typer.Option(..., "--content", help="Thread content"),
    chapter: str = typer.Option(None, "--chapter", help="Chapter placeholder"),
) -> None:
    """Plant a new narrative thread in a workspace."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    thread = plant_thread(db, workspace_id, kind=kind, content=content, chapter=chapter)
    typer.echo(f"planted {thread.id} [{KIND_LABELS[thread.kind]}] {thread.content}")
    _record_proactive(
        db,
        workspace_id,
        proactive.TRIGGER_PLOT_PLANTED,
        {"content": thread.content, "kind": thread.kind, "chapter": thread.chapter or ""},
    )


@plot_app.command("list")
def plot_list(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """List every narrative thread in a workspace."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    threads = list_threads(db, workspace_id)
    if not threads:
        typer.echo("no plot threads yet")
        return
    for thread in threads:
        label = KIND_LABELS.get(thread.kind, thread.kind)
        chapter = thread.chapter or "-"
        typer.echo(f"{thread.id}  [{label}]  {thread.status}  {chapter}  {thread.content}")


@plot_app.command("recover")
def plot_recover(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    thread_id: str = typer.Argument(..., help="Plot thread id"),
) -> None:
    """Mark a narrative thread as recovered."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    thread, changed = recover_thread(db, workspace_id, thread_id)
    label = KIND_LABELS.get(thread.kind, thread.kind)
    if changed:
        typer.echo(f"recovered {thread.id} [{label}]")
    else:
        typer.echo(f"already recovered {thread.id} [{label}]")
