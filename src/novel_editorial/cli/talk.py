"""Talk command group."""

from __future__ import annotations

import json

import typer

from novel_editorial.core import proactive
from novel_editorial.core.behavior import record_behavior_entry_safe
from novel_editorial.core.chat import (
    AUTHOR_ACTOR,
    MOOD_ACCEPTED,
    MOOD_TALK,
    PROACTIVE_PAYLOAD,
    PROACTIVE_QUESTION,
    build_agent_prompt,
    check_refusal,
    get_agent,
    get_workspace_or_raise,
    has_proactive_message,
    has_same_rule_override,
    has_same_rule_refusal,
    is_author_override,
    list_messages,
    record_message,
    resolve_target_role,
    update_agent_mood,
)
from novel_editorial.core.config import load_settings
from novel_editorial.llm.client import LLMMessage, build_client
from novel_editorial.store.db import DB
from novel_editorial.store.models import AgentRole, StyleAnchor

talk_app = typer.Typer(help="Talk with the editorial band")


def _has_style_anchor(db: DB, workspace_id: str) -> bool:
    """True when the workspace has a meaningful style anchor (non-empty description)."""
    with db.workspace_session(workspace_id) as session:
        anchor = session.query(StyleAnchor).filter_by(workspace_id=workspace_id).first()
        return bool(anchor and anchor.description)


def _record_proactive(db: DB, workspace_id: str, trigger: str, context: dict) -> None:
    """Evaluate and echo proactive messages; a failure never rolls business back."""
    try:
        messages = proactive.record_proactive_messages(db, workspace_id, trigger, context)
    except Exception as exc:
        typer.echo(f"warning: proactive messages skipped: {exc}", err=True)
        return
    for message in messages:
        typer.echo(f"{message.actor}: {message.content}")


def _proactive_kind(payload: str | None) -> str | None:
    """Return the proactive kind carried by an agent-initiated message payload.

    Only messages whose payload marks them as agent-initiated and whose kind is
    one of the registered proactive kinds are classified; everything else
    (plain dialogue, refusal, mood_change, malformed payloads) returns None.
    """
    try:
        data = json.loads(payload or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("initiator") != proactive.INITIATOR_AGENT:
        return None
    kind = data.get("kind")
    return kind if isinstance(kind, str) and kind in proactive.PROACTIVE_KINDS else None


DISAGREEMENT_MARKS: dict[str, str] = {
    "refusal": "拒绝",
    "rebuttal": "反驳",
    "override": "推翻",
}


def _disagreement_mark(payload: str | None) -> str | None:
    """Return the disagreement mark for refusal/rebuttal/override payloads.

    Malformed, non-object, and unknown-kind payloads return None so the
    message keeps its plain role prefix instead of crashing the listing.
    """
    try:
        data = json.loads(payload or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    kind = data.get("kind")
    if not isinstance(kind, str):
        return None
    return DISAGREEMENT_MARKS.get(kind)


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
    rule = check_refusal(agent, message)
    if rule is not None and is_author_override(message):
        record_message(db, workspace_id, role="author", actor=AUTHOR_ACTOR, content=message)
        content = rule.acceptance
        payload = {"kind": "override", "stance": rule.stance, "rule": rule.rule}
        record_message(
            db,
            workspace_id,
            role="agent",
            actor=agent.name,
            content=content,
            payload=payload,
        )
        update_agent_mood(db, workspace_id, agent, MOOD_ACCEPTED)
        record_behavior_entry_safe(
            db,
            workspace_id,
            agent_id=agent.id,
            kind="viewpoint",
            target=rule.rule,
            summary="作者推翻后调整",
            before_value="坚持该立场",
            after_value="按作者决定执行",
            source=f"override:{rule.rule}",
        )
        record_behavior_entry_safe(
            db,
            workspace_id,
            agent_id=agent.id,
            kind="relationship",
            target=AUTHOR_ACTOR,
            summary="作者拍板优先",
            source=f"override:{rule.rule}",
        )
        typer.echo(f"{AUTHOR_ACTOR}: {message}")
        typer.echo(f"{agent.name}: {content}")
        return
    if rule is not None and not has_same_rule_override(db, workspace_id, agent, rule.rule):
        record_message(db, workspace_id, role="author", actor=AUTHOR_ACTOR, content=message)
        repeated = has_same_rule_refusal(db, workspace_id, agent, rule.rule)
        content = rule.reaffirmation if repeated else rule.refusal
        payload: dict[str, object] = {
            "kind": "refusal",
            "stance": rule.stance,
            "rule": rule.rule,
        }
        if repeated:
            payload["repeated"] = True
        record_message(
            db,
            workspace_id,
            role="agent",
            actor=agent.name,
            content=content,
            payload=payload,
        )
        update_agent_mood(db, workspace_id, agent, MOOD_TALK)
        if not repeated:
            record_behavior_entry_safe(
                db,
                workspace_id,
                agent_id=agent.id,
                kind="viewpoint",
                target=rule.rule,
                summary="拒绝了违背立场的指令",
                after_value="坚持该立场",
                source=f"refusal:{rule.rule}",
            )
        typer.echo(f"{AUTHOR_ACTOR}: {message}")
        typer.echo(f"{agent.name}: {content}")
        return
    # A rule already overridden by the author falls through to the normal LLM
    # path; the stance stays in the prompt and the override record stays traced.
    history = list_messages(db, workspace_id)
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
        _record_proactive(
            db,
            workspace_id,
            proactive.TRIGGER_TALK_FIRST_ROUND,
            {
                "first_round": True,
                "has_style_anchor": _has_style_anchor(db, workspace_id),
            },
        )


@talk_app.command("list")
def talk_list(workspace_id: str = typer.Argument(..., help="Workspace id")) -> None:
    """List the conversation, marking proactive and disagreement messages."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()
    get_workspace_or_raise(db, workspace_id)
    for message in list_messages(db, workspace_id):
        kind = _proactive_kind(message.payload)
        if kind is not None:
            typer.echo(f"[agent·主动·{kind}] {message.actor}: {message.content}")
            continue
        mark = _disagreement_mark(message.payload)
        if mark is not None and message.role == "agent":
            typer.echo(f"[agent·分歧·{mark}] {message.actor}: {message.content}")
            continue
        typer.echo(f"[{message.role}] {message.actor}: {message.content}")
