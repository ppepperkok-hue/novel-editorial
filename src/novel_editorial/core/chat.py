"""Conversation services for the editorial band."""

from __future__ import annotations

import json
import re

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, AgentRole, Message, Workspace

AUTHOR_ACTOR = "作者"
PROACTIVE_PAYLOAD = {"initiator": "agent", "kind": "proactive_question"}
PROACTIVE_QUESTION = (
    "我想先确认一下：这部作品的主角动机和核心冲突，咱们还没对齐吧？"
    "这个定不下来，后面每一章都会飘。"
)

ROLE_ALIASES: dict[str, str] = {
    "总编": AgentRole.EDITOR_IN_CHIEF,
    "主编": AgentRole.EDITOR_IN_CHIEF,
    "责编": AgentRole.EDITOR,
    "写手": AgentRole.WRITER,
    "审稿": AgentRole.REVIEWER,
}

def get_workspace_or_raise(db: DB, workspace_id: str) -> Workspace:
    with db.global_session() as session:
        workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise NovelError(ErrorCode.NOT_FOUND, f"workspace not found: {workspace_id}")
    return workspace


def get_agent(db: DB, workspace_id: str, role: str) -> Agent:
    with db.workspace_session(workspace_id) as session:
        agent = session.query(Agent).filter_by(workspace_id=workspace_id, role=role).first()
    if agent is None:
        raise NovelError(ErrorCode.NOT_FOUND, f"agent not found in workspace: {role}")
    return agent


def record_message(
    db: DB,
    workspace_id: str,
    *,
    role: str,
    actor: str,
    content: str,
    payload: dict | None = None,
) -> Message:
    with db.workspace_session(workspace_id) as session:
        message = Message(
            workspace_id=workspace_id,
            role=role,
            actor=actor,
            content=content,
            payload=json.dumps(payload or {}, ensure_ascii=False),
        )
        session.add(message)
        session.commit()
        return message


def list_messages(db: DB, workspace_id: str) -> list[Message]:
    with db.workspace_session(workspace_id) as session:
        return session.query(Message).order_by(Message.created_at).all()


def has_proactive_message(db: DB, workspace_id: str) -> bool:
    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(Message)
            .filter(
                Message.workspace_id == workspace_id,
                Message.payload.like('%"kind": "proactive_question"%'),
            )
            .first()
        )
    return row is not None


def resolve_target_role(message: str) -> str:
    match = re.search(r"@([^，。：；！？、,.;:!?\s]+)", message)
    if match is None:
        return AgentRole.EDITOR_IN_CHIEF
    alias = match.group(1)
    role = ROLE_ALIASES.get(alias)
    if role is None:
        raise NovelError(ErrorCode.USAGE_ERROR, f"unknown partner alias: {alias}")
    return role


def build_agent_prompt(
    workspace: Workspace,
    agent: Agent,
    history: list[Message],
    latest_message: str | None = None,
) -> str:
    lines = [
        f"你是作品《{workspace.title}》的{agent.name}（{agent.role}）。",
        f"你的性格：{agent.personality}",
        f"你的立场：{agent.stance}",
        f"作品简介：{workspace.title}（{workspace.genre}）{workspace.description}".rstrip(),
        "最近对话：",
    ]
    for message in history[-6:]:
        lines.append(f"{message.actor}: {message.content}")
    if latest_message:
        lines.append(f"{AUTHOR_ACTOR}刚刚说：{latest_message}")
    lines.append(f"请以{agent.name}的身份回应，不要超出你的立场。")
    return "\n".join(lines)
