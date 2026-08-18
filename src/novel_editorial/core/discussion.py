"""N4 editorial discussion: structured multi-partner discussion round (E1)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import literal_column

from novel_editorial.core.chat import AUTHOR_ACTOR, _record_message_in_session
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
    payload = {
        "kind": "discussion_contribution",
        "discussion_id": discussion_id,
        "topic": topic,
        "position": "stated",
    }
    with db.workspace_session(workspace_id) as session:
        message = _record_message_in_session(
            session,
            workspace_id,
            role="agent",
            actor=agent.name,
            content=template.format(topic=topic),
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


def summarize_discussion(
    db: DB,
    workspace_id: str,
    *,
    discussion_id: str,
    topic: str,
    summarizer: Agent,
) -> Message:
    """Summarize every contribution deterministically; the author keeps the call."""
    if not _discussion_exists(db, workspace_id, discussion_id):
        raise NovelError(ErrorCode.NOT_FOUND, f"discussion not found: {discussion_id}")
    contributions = _discussion_contributions(db, workspace_id, discussion_id)
    if not contributions:
        raise NovelError(ErrorCode.USAGE_ERROR, "discussion 还没有任何发言")

    positions = [
        {
            "agent": message.actor,
            "position": "stated",
            "content": message.content,
        }
        for message in contributions
    ]
    body = "\n".join(f"{message.actor}：{message.content}" for message in contributions)
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
