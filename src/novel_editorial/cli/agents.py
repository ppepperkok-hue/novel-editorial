"""Agents command group."""

from __future__ import annotations

import typer

from novel_editorial.core.agents import resolve_agent, update_agent_field
from novel_editorial.core.behavior import current_behavior_state
from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, Workspace

agents_app = typer.Typer(help="Manage editorial partners")


@agents_app.command("show")
def agents_show(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """Show the workspace's editorial band with full profiles."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    with db.global_session() as session:
        if session.get(Workspace, workspace_id) is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"workspace not found: {workspace_id}")
    with db.workspace_session(workspace_id) as session:
        agents = session.query(Agent).order_by(Agent.created_at).all()
    state = current_behavior_state(db, workspace_id)
    for agent in agents:
        typer.echo(f"[{agent.role}] {agent.name}")
        typer.echo(f"  当前状态: {agent.mood}")
        typer.echo(f"  性格: {agent.personality}")
        typer.echo(f"  立场: {agent.stance}")
        typer.echo(f"  价值观: {agent.values}")
        typer.echo(f"  审美: {agent.aesthetic}")
        typer.echo(f"  情绪基线: {agent.emotion_baseline}")
        typer.echo(f"  工作习惯: {agent.work_habits}")
        typer.echo(f"  弱点: {agent.weaknesses}")
        typer.echo(f"  人际预设: {agent.relationship_presets}")
        typer.echo(f"  私心: {agent.private_motive}")
        summaries = sorted(
            (
                entry
                for (agent_id, kind, _target), entry in state.items()
                if agent_id == agent.id and kind in ("impression", "relationship")
            ),
            key=lambda entry: (entry.kind, entry.target),
        )
        if summaries:
            typer.echo("  印象与关系:")
            for entry in summaries:
                typer.echo(f"    {entry.kind} -> {entry.target}: {entry.summary}")


@agents_app.command("edit")
def agents_edit(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    target: str = typer.Argument(..., help="Agent id or alias (总编/责编/写手/审稿)"),
    field: str = typer.Option(..., "--field", help="Profile field to edit"),
    value: str = typer.Option(..., "--value", help="New value"),
) -> None:
    """Edit one profile field of an agent."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    agent = resolve_agent(db, workspace_id, target)
    update_agent_field(db, workspace_id, agent.id, field=field, value=value)
    typer.echo(f"{agent.name} {field} updated")
