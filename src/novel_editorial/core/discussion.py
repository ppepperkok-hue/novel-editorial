"""N4 editorial discussion: structured multi-partner discussion round (E2)."""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Sequence

from sqlalchemy import literal_column

from novel_editorial.core.behavior import record_behavior_entry_safe
from novel_editorial.core.chat import (
    AUTHOR_ACTOR,
    MOOD_TALK,
    _record_message_in_session,
    check_refusal,
    has_same_rule_override,
    has_same_rule_refusal,
    update_agent_mood,
)
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, AgentRole, Message

CONTRIBUTION_TEMPLATES: dict[str, str] = {
    AgentRole.EDITOR_IN_CHIEF: "关于「{topic}」，我先定个基调：主线不能散，整体稳了再谈细节。",
    AgentRole.EDITOR: "关于「{topic}」，我谈节奏：钩子和信息密度要稳住，读者追读靠这个。",
    AgentRole.WRITER: "关于「{topic}」，我守人设：人物逻辑是底线，不能为剧情强行降智。",
    AgentRole.REVIEWER: "关于「{topic}」，我盯一致性：伏笔和时间线前后要咬合，出洞我第一个退稿。",
}

SUMMARY_LEAD = "围绕「{topic}」，各方的表态汇总如下："


def _require_non_empty(value: str, label: str) -> None:
    if not value.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, f"{label} 不能为空")


def open_discussion(
    db: DB,
    workspace_id: str,
    *,
    topic: str,
    participants: Sequence[Agent],
) -> tuple[str, Message]:
    """Open one discussion round with an author-led kickoff message."""
    _require_non_empty(topic, "topic")
    if not participants:
        raise NovelError(ErrorCode.USAGE_ERROR, "participants 不能为空")
    roles = [agent.role for agent in participants]
    if len(set(roles)) != len(roles):
        raise NovelError(ErrorCode.USAGE_ERROR, "participants 角色不能重复")

    discussion_id = uuid.uuid4().hex
    names = [agent.name for agent in participants]
    payload = {
        "kind": "discussion_open",
        "discussion_id": discussion_id,
        "topic": topic,
        "participants": names,
        "convener": AUTHOR_ACTOR,
    }
    content = f"作者发起讨论「{topic}」（参与：{'、'.join(names)}）"
    with db.workspace_session(workspace_id) as session:
        message = _record_message_in_session(
            session,
            workspace_id,
            role="author",
            actor=AUTHOR_ACTOR,
            content=content,
            payload=payload,
        )
        session.commit()
    return discussion_id, message


def contribute_to_discussion(
    db: DB,
    workspace_id: str,
    *,
    discussion_id: str,
    topic: str,
    agent: Agent,
) -> Message:
    """Record one partner's deterministic stance in the discussion round."""
    template = CONTRIBUTION_TEMPLATES.get(agent.role)
    if template is None:
        raise NovelError(ErrorCode.USAGE_ERROR, f"不支持的讨论角色: {agent.role}")
    payload: dict[str, object] = {
        "kind": "discussion_contribution",
        "discussion_id": discussion_id,
        "topic": topic,
        "position": "stated",
    }
    rule = check_refusal(agent, topic)
    if rule is not None and not has_same_rule_override(
        db, workspace_id, agent, rule.rule
    ):
        repeated = has_same_rule_refusal(db, workspace_id, agent, rule.rule)
        content = rule.reaffirmation if repeated else rule.refusal
        payload["position"] = "refused"
        payload["rule"] = rule.rule
        payload["stance"] = rule.stance
        if repeated:
            payload["repeated"] = True
    else:
        content = template.format(topic=topic)
    with db.workspace_session(workspace_id) as session:
        message = _record_message_in_session(
            session,
            workspace_id,
            role="agent",
            actor=agent.name,
            content=content,
            payload=payload,
        )
        session.commit()
    return message


def _discussion_exists(db: DB, workspace_id: str, discussion_id: str) -> bool:
    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(Message)
            .filter(
                Message.workspace_id == workspace_id,
                Message.payload.like('%"kind": "discussion_open"%'),
                Message.payload.like(f'%"discussion_id": "{discussion_id}"%'),
            )
            .first()
        )
    return row is not None


def _discussion_contributions(
    db: DB, workspace_id: str, discussion_id: str
) -> list[Message]:
    """Return every contribution for one discussion in insertion order."""
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(Message)
            .filter(
                Message.workspace_id == workspace_id,
                Message.payload.like('%"kind": "discussion_contribution"%'),
                Message.payload.like(f'%"discussion_id": "{discussion_id}"%'),
            )
            .order_by(literal_column("rowid"))
            .all()
        )


def _discussion_summary(db: DB, workspace_id: str, discussion_id: str) -> Message | None:
    """Return the existing summary for one discussion, if any."""
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(Message)
            .filter(
                Message.workspace_id == workspace_id,
                Message.payload.like('%"kind": "discussion_summary"%'),
                Message.payload.like(f'%"discussion_id": "{discussion_id}"%'),
            )
            .order_by(literal_column("rowid"))
            .first()
        )


def _parse_contribution_payload(message: Message) -> dict[str, object]:
    """Decode one contribution payload; malformed payloads fall back to empty."""
    try:
        data = json.loads(message.payload or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _get_agent_by_name(db: DB, workspace_id: str, name: str) -> Agent | None:
    """Fetch one partner by name; None when the actor is not a band member."""
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, name=name)
            .first()
        )


def _trace_discussion_sediment(
    db: DB,
    workspace_id: str,
    *,
    discussion_id: str,
    topic: str,
    message: Message,
    entry: dict[str, object],
) -> None:
    """Append one partner's viewpoint and mood trace; failures only warn."""
    agent = _get_agent_by_name(db, workspace_id, message.actor)
    if agent is None:
        print(
            f"warning: discussion sediment skipped: agent not found: {message.actor}",
            file=sys.stderr,
        )
        return
    refused = entry["position"] == "refused"
    summary = "拒绝了违背立场的议题" if refused else "表达了立场"
    after_value = "拒绝参与该议题并坚持立场" if refused else "表达了立场"
    record_behavior_entry_safe(
        db,
        workspace_id,
        agent_id=agent.id,
        kind="viewpoint",
        target=topic,
        summary=summary,
        after_value=after_value,
        source=f"discussion:{discussion_id}",
    )
    try:
        update_agent_mood(db, workspace_id, agent, MOOD_TALK)
    except Exception as exc:
        print(f"warning: mood trace skipped: {exc}", file=sys.stderr)


def summarize_discussion(
    db: DB,
    workspace_id: str,
    *,
    discussion_id: str,
    topic: str,
    summarizer: Agent,
) -> Message:
    """Summarize every contribution deterministically; idempotent per discussion."""
    if not _discussion_exists(db, workspace_id, discussion_id):
        raise NovelError(ErrorCode.NOT_FOUND, f"discussion not found: {discussion_id}")
    existing = _discussion_summary(db, workspace_id, discussion_id)
    if existing is not None:
        return existing
    contributions = _discussion_contributions(db, workspace_id, discussion_id)
    if not contributions:
        raise NovelError(ErrorCode.USAGE_ERROR, "discussion 还没有任何发言")

    positions: list[dict[str, object]] = []
    body_lines: list[str] = []
    for message in contributions:
        contribution_payload = _parse_contribution_payload(message)
        refused = contribution_payload.get("position") == "refused"
        entry: dict[str, object] = {
            "agent": message.actor,
            "position": "refused" if refused else "stated",
            "content": message.content,
        }
        if refused:
            entry["rule"] = contribution_payload.get("rule", "")
            entry["stance"] = contribution_payload.get("stance", "")
            body_lines.append(f"{message.actor}：{message.content}【分歧】")
        else:
            body_lines.append(f"{message.actor}：{message.content}")
        positions.append(entry)
    body = "\n".join(body_lines)
    payload = {
        "kind": "discussion_summary",
        "discussion_id": discussion_id,
        "topic": topic,
        "positions": positions,
    }
    content = f"{SUMMARY_LEAD.format(topic=topic)}\n{body}"
    with db.workspace_session(workspace_id) as session:
        message = _record_message_in_session(
            session,
            workspace_id,
            role="agent",
            actor=summarizer.name,
            content=content,
            payload=payload,
        )
        session.commit()
    for contribution, entry in zip(contributions, positions, strict=True):
        _trace_discussion_sediment(
            db,
            workspace_id,
            discussion_id=discussion_id,
            topic=topic,
            message=contribution,
            entry=entry,
        )
    return message


def conclude_discussion(
    db: DB,
    workspace_id: str,
    *,
    discussion_id: str,
    topic: str,
    outcome: str,
) -> Message:
    """Record the author's final decision that closes the discussion round."""
    _require_non_empty(outcome, "outcome")
    if not _discussion_exists(db, workspace_id, discussion_id):
        raise NovelError(ErrorCode.NOT_FOUND, f"discussion not found: {discussion_id}")
    payload = {
        "kind": "discussion_decision",
        "discussion_id": discussion_id,
        "topic": topic,
        "outcome": outcome,
    }
    with db.workspace_session(workspace_id) as session:
        message = _record_message_in_session(
            session,
            workspace_id,
            role="author",
            actor=AUTHOR_ACTOR,
            content=f"作者拍板：{outcome}",
            payload=payload,
        )
        session.commit()
    return message
