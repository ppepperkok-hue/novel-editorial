"""Talk command group."""

from __future__ import annotations

import typer

from novel_editorial.core.chat import (
    AUTHOR_ACTOR,
    MOOD_TALK,
    PROACTIVE_PAYLOAD,
    PROACTIVE_QUESTION,
    build_agent_prompt,
    check_refusal,
    get_agent,
    get_workspace_or_raise,
    has_proactive_message,
    list_messages,
    record_message,
    resolve_target_role,
    update_agent_mood,
)
from novel_editorial.core.config import load_settings
from novel_editorial.llm.client import LLMMessage
from novel_editorial.store.db import DB
from novel_editorial.store.models import AgentRole

talk_app = typer.Typer(help="Talk with the editorial band")


@talk_app.command("send")
def talk_send(
    workspace_id: str = typer.Argument(..., help="Workspace id"),
    message: str = typer.Argument(..., help="Message to the band"),
) -> None:
    """Send one message to the band; the addressed partner replies."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    workspace = get_workspace_or_raise(db, workspace_id)

    target_role = resolve_target_role(message)
    agent = get_agent(db, workspace_id, target_role)
    refusal = check_refusal(agent, message)
    if refusal:
        record_message(db, workspace_id, role="author", actor=AUTHOR_ACTOR, content=message)
        record_message(
            db,
            workspace_id,
            role="agent",
            actor=agent.name,
            content=refusal,
            payload={"kind": "refusal"},
        )
        update_agent_mood(db, workspace_id, agent, MOOD_TALK)
        typer.echo(f"{AUTHOR_ACTOR}: {message}")
        typer.echo(f"{agent.name}: {refusal}")
        return
    history = list_messages(db, workspace_id)
    # Resolve lazily from cli.app so existing tests' monkeypatch of
    # novel_editorial.cli.app.build_client keeps taking effect.
    from novel_editorial.cli.app import build_client

    client = build_client(settings)
    prompt = build_agent_prompt(
        workspace,
        agent,
        history,
        latest_message=message,
        db=db,
        workspace_id=workspace_id,
    )
    reply = client.complete([LLMMessage(role="user", content=prompt)]).content
    record_message(db, workspace_id, role="author", actor=AUTHOR_ACTOR, content=message)
    record_message(db, workspace_id, role="agent", actor=agent.name, content=reply)
    update_agent_mood(db, workspace_id, agent, MOOD_TALK)

    typer.echo(f"{AUTHOR_ACTOR}: {message}")
    typer.echo(f"{agent.name}: {reply}")

    if not has_proactive_message(db, workspace_id):
        editor = get_agent(db, workspace_id, AgentRole.EDITOR)
        record_message(
            db,
            workspace_id,
            role="agent",
            actor=editor.name,
            content=PROACTIVE_QUESTION,
            payload=PROACTIVE_PAYLOAD,
        )
        typer.echo(f"{editor.name}: {PROACTIVE_QUESTION}")


@talk_app.command("list")
def talk_list(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """List the conversation history for a workspace."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    for message in list_messages(db, workspace_id):
        typer.echo(f"[{message.role}] {message.actor}: {message.content}")
