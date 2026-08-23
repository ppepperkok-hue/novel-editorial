"""Delegation conversation model: partners delegate tasks and respond.

Delegation verdicts are the N28-A feedback source for the delegating partner:
after the response message commits, a refusal creates/strengthens the
delegator's pending_issue motive and boosts the delegator's stubbornness
drift, while an acceptance resolves the delegator's pending_issue motive and
boosts the delegator's proactivity drift. Every write-back runs through the
safe entry points (post-hoc, warning-only on failure) so a motive or drift
failure never rolls the delegation response back.
"""

from __future__ import annotations

from novel_editorial.core.behavior import record_behavior_entry_safe
from novel_editorial.core.chat import (
    _record_message_in_session,
    apply_drift_safe,
    check_refusal,
    has_same_rule_override,
    has_same_rule_refusal,
)
from novel_editorial.core.motives import clear_motives_safe, upsert_motive_feedback_safe
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, Message, MotiveKind

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
    reaffirms the stance with the rule's reaffirmation wording. After the
    message and event commit, N3 sediment is appended via the safe entry point:
    acceptance traces a relationship and an impression from the delegator to
    the delegated partner, refusal traces the delegator's relationship plus a
    first-time viewpoint held by the delegated partner. A trace failure only
    warns on stderr and never rolls the business result back.
    """
    rule = check_refusal(to_agent, task)
    if rule is not None and not has_same_rule_override(
        db, workspace_id, to_agent, rule.rule
    ):
        refused = True
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
        refused = False
        repeated = False
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
    if refused:
        assert rule is not None
        record_behavior_entry_safe(
            db,
            workspace_id,
            agent_id=from_agent.id,
            kind="relationship",
            target=to_agent.name,
            summary="委托被拒绝",
            source="delegation:refused",
        )
        if not repeated:
            record_behavior_entry_safe(
                db,
                workspace_id,
                agent_id=to_agent.id,
                kind="viewpoint",
                target=rule.rule,
                summary="拒绝了违背立场的指令",
                after_value="坚持该立场",
                source=f"refusal:{rule.rule}",
            )
        # N28-A write-backs (post-hoc, safe-degraded): a refused delegation
        # leaves the delegator holding the issue and more stubborn.
        upsert_motive_feedback_safe(
            db,
            workspace_id,
            from_agent.id,
            kind=MotiveKind.PENDING_ISSUE.value,
            content="委托被拒，这事还惦记着",
            source="delegation:refused",
        )
        apply_drift_safe(
            db,
            workspace_id,
            from_agent.id,
            "stubbornness",
            1,
            event="delegation:refused",
        )
    else:
        record_behavior_entry_safe(
            db,
            workspace_id,
            agent_id=from_agent.id,
            kind="relationship",
            target=to_agent.name,
            summary="委托被接受",
            source="delegation:accepted",
        )
        record_behavior_entry_safe(
            db,
            workspace_id,
            agent_id=from_agent.id,
            kind="impression",
            target=to_agent.name,
            summary="可协作",
            source="delegation:accepted",
        )
        # N28-A write-backs (post-hoc, safe-degraded): an accepted delegation
        # resolves the delegator's pending issue (from earlier refusals) and
        # the delegator is energized to keep asking.
        clear_motives_safe(
            db,
            workspace_id,
            agent_id=from_agent.id,
            kind=MotiveKind.PENDING_ISSUE.value,
            source="delegation:refused",
        )
        apply_drift_safe(
            db,
            workspace_id,
            from_agent.id,
            "proactivity",
            1,
            event="delegation:accepted",
        )
    return message
