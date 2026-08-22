"""Motives command group (N27 S1): inspect what partners are carrying."""

from __future__ import annotations

import typer

from novel_editorial.core.agents import resolve_agent
from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.config import load_settings
from novel_editorial.core.motives import list_motives
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent

motives_app = typer.Typer(help="Inspect partner motives")


def _agent_names(db: DB, workspace_id: str) -> dict[str, str]:
    with db.workspace_session(workspace_id) as session:
        agents = session.query(Agent).filter_by(workspace_id=workspace_id).all()
    return {agent.id: agent.name for agent in agents}


@motives_app.command("list")
def motives_list(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    agent: str | None = typer.Option(
        None,
        "--agent",
        help="Agent id or alias (总编/责编/写手/审稿); omit for every partner",
    ),
) -> None:
    """List partner motives with kind, strength, source and last touch."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    agent_id: str | None = None
    agent_name: str | None = None
    if agent is not None:
        resolved = resolve_agent(db, workspace_id, agent)
        agent_id = resolved.id
        agent_name = resolved.name
    motives = list_motives(db, workspace_id, agent_id=agent_id)
    if not motives:
        if agent_name is not None:
            typer.echo(f"no motives for {agent_name}")
        else:
            typer.echo("no motives yet")
        return
    names = _agent_names(db, workspace_id)
    for motive in motives:
        owner = names.get(motive.agent_id, motive.agent_id)
        touched = motive.last_touched_at.isoformat(timespec="seconds")
        typer.echo(
            f"{motive.id} [{owner}] [{motive.kind}] strength={motive.strength} "
            f"source={motive.source} touched={touched} {motive.content}"
        )
