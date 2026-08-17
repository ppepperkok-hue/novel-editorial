"""Behavior command group: inspect behavior traces and evolution."""

from __future__ import annotations

import typer

from novel_editorial.core.agents import resolve_agent
from novel_editorial.core.behavior import (
    BEHAVIOR_KINDS,
    current_behavior_state,
    list_behavior_timeline,
)
from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, BehaviorTimeline

behavior_app = typer.Typer(help="Inspect behavior traces and evolution")

_KINDS_OPTION = typer.Option(None, "--kind", help="Filter by behavior kind (repeatable)")


def _has_change(entry: BehaviorTimeline) -> bool:
    return bool(entry.before_value or entry.after_value)


def _resolve_kinds(kinds: list[str] | None) -> list[str] | None:
    if not kinds:
        return None
    resolved = list(dict.fromkeys(kinds))
    for kind in resolved:
        if kind not in BEHAVIOR_KINDS:
            expected = ", ".join(BEHAVIOR_KINDS)
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                f"unknown behavior kind: {kind} (expected one of: {expected})",
            )
    return resolved


def _resolve_agent_id(db: DB, workspace_id: str, target: str) -> str:
    try:
        return resolve_agent(db, workspace_id, target).id
    except NovelError as exc:
        if exc.code is ErrorCode.NOT_FOUND:
            raise NovelError(ErrorCode.USAGE_ERROR, f"unknown agent: {target}") from exc
        raise


def _agent_names(db: DB, workspace_id: str) -> dict[str, str]:
    with db.workspace_session(workspace_id) as session:
        agents = session.query(Agent).all()
    return {agent.id: agent.name for agent in agents}


def _render_timeline_line(entry: BehaviorTimeline, agent_name: str) -> str:
    line = (
        f"{entry.created_at.isoformat(timespec='seconds')} [{entry.kind}] "
        f"{agent_name} -> {entry.target}: {entry.summary}"
    )
    if _has_change(entry):
        line += f" | {entry.before_value or '无'} -> {entry.after_value or '无'}"
    if entry.source:
        line += f" | source={entry.source}"
    return line


@behavior_app.command("timeline")
def behavior_timeline(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    agent: str | None = typer.Option(None, "--agent", help="Filter by agent alias or id"),
    kinds: list[str] | None = _KINDS_OPTION,
    limit: int = typer.Option(20, "--limit", min=1, help="Max entries to show"),
) -> None:
    """Replay behavior traces oldest first."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    agent_id = _resolve_agent_id(db, workspace_id, agent) if agent else None
    resolved_kinds = _resolve_kinds(kinds)

    entries = list_behavior_timeline(
        db, workspace_id, agent_id=agent_id, kind=resolved_kinds, limit=limit
    )

    if not entries:
        typer.echo("no behavior traces yet")
        return
    names = _agent_names(db, workspace_id)
    for entry in entries:
        typer.echo(_render_timeline_line(entry, names.get(entry.agent_id, entry.agent_id)))


@behavior_app.command("show")
def behavior_show(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """Show each partner's current impression, relationship, and viewpoint state."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    state = current_behavior_state(db, workspace_id)
    if not state:
        typer.echo("no behavior traces yet")
        return
    with db.workspace_session(workspace_id) as session:
        agents = session.query(Agent).order_by(Agent.created_at).all()
    printed = False
    for agent in agents:
        entries = [
            entry for (agent_id, _kind, _target), entry in state.items() if agent_id == agent.id
        ]
        if not entries:
            continue
        printed = True
        typer.echo(f"[{agent.name}]")
        for entry in sorted(entries, key=lambda item: (item.kind, item.target)):
            line = f"  {entry.kind} -> {entry.target}: {entry.summary}"
            if _has_change(entry):
                line += f"（{entry.before_value or '无'} -> {entry.after_value or '无'}）"
            typer.echo(line)
    if not printed:
        typer.echo("no behavior traces yet")
