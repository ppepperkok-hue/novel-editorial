"""Delegation conversation model: partners delegate tasks and respond."""

from __future__ import annotations

from novel_editorial.core.chat import (
    _record_message_in_session,
    check_refusal,
    has_same_rule_override,
    has_same_rule_refusal,
)
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, Message

ACCEPT_REPLY = "收到，我这就看。"


def record_delegation(
    db: DB,
    workspace_id: str,
    from_agent: Agent,
    to_agent: Agent,
    task: str,
) -> Message:
    """Record one partner delegating a task to another partner.

    The delegation is a conversation message, not a work order: no queue, no
    state machine, no deadline. The agent.message event rides along with the
    message and both commit in one transaction.
    """
    payload = {
        "initiator": "agent",
        "kind": "delegation",
        "from": from_agent.name,
        "to": to_agent.name,
        "task": task,
    }
    with db.workspace_session(workspace_id) as session:
        message = _record_message_in_session(
            session,
            workspace_id,
            role="agent",
            actor=from_agent.name,
            content=f"{from_agent.name} 委托 {to_agent.name}：{task}",
            payload=payload,
        )
        session.commit()
        return message


def respond_to_delegation(
    db: DB,
    workspace_id: str,
    from_agent: Agent,
    to_agent: Agent,
    task: str,
) -> Message:
    """Record the delegated partner's deterministic reply.

    The reply follows the N2 stance rules with the same history checks as talk
    send: an already-overridden rule accepts with the fixed reply, a first rule
    hit refuses with the rule's refusal wording, and a repeated rule hit
    reaffirms the stance with the rule's reaffirmation wording.
    """
    rule = check_refusal(to_agent, task)
    if rule is not None and not has_same_rule_override(
        db, workspace_id, to_agent, rule.rule
    ):
        repeated = has_same_rule_refusal(db, workspace_id, to_agent, rule.rule)
        content = rule.reaffirmation if repeated else rule.refusal
        payload: dict[str, object] = {
            "initiator": "agent",
            "kind": "delegation_response",
            "decision": "refused",
            "rule": rule.rule,
            "stance": rule.stance,
        }
        if repeated:
            payload["repeated"] = True
    else:
        content = ACCEPT_REPLY
        payload = {
            "initiator": "agent",
            "kind": "delegation_response",
            "decision": "accepted",
        }
    with db.workspace_session(workspace_id) as session:
        message = _record_message_in_session(
            session,
            workspace_id,
            role="agent",
            actor=to_agent.name,
            content=content,
            payload=payload,
        )
        session.commit()
        return message
