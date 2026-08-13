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

REFUSAL_RULES: dict[str, list[tuple[tuple[str, ...], str]]] = {
    AgentRole.WRITER: [
        (
            ("违背人设", "强行降智", "无视设定", "乱改设定"),
            "这个我写不了。违背人物逻辑的剧情，写出来也是假的，我的立场不允许。",
        ),
    ],
    AgentRole.REVIEWER: [
        (
            ("放行", "忽略矛盾", "别管矛盾", "忽略逻辑", "别查伏笔", "直接过", "别较真"),
            "这个我不能放行。前后矛盾不修就过稿，等于砸审稿的招牌。",
        ),
    ],
    AgentRole.EDITOR: [
        (
            ("删掉钩子", "删钩子", "钩子全删", "不要钩子", "平铺直叙", "不要节奏"),
            "钩子删光、节奏放平，读者留不住。这稿我不接，先改回来再说。",
        ),
    ],
}

NEGATION_PREFIXES = ("不", "别", "勿", "莫", "不必")


def _keyword_triggered(message: str, keyword: str) -> bool:
    """True if the keyword appears in the message without a negation prefix."""
    start = 0
    while True:
        index = message.find(keyword, start)
        if index == -1:
            return False
        prefix = message[max(0, index - 2) : index]
        if not any(negation in prefix for negation in NEGATION_PREFIXES):
            return True
        start = index + 1


def check_refusal(agent: Agent, message: str) -> str | None:
    """Return a refusal text if the message conflicts with the agent's stance."""
    for keywords, refusal in REFUSAL_RULES.get(agent.role, []):
        if any(_keyword_triggered(message, keyword) for keyword in keywords):
            return refusal
    return None

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
        f"你的价值观：{agent.values}",
        f"你的审美：{agent.aesthetic}",
        f"你的工作习惯：{agent.work_habits}",
        f"作品简介：{workspace.title}（{workspace.genre}）{workspace.description}".rstrip(),
        "最近对话：",
    ]
    for message in history[-6:]:
        lines.append(f"{message.actor}: {message.content}")
    if latest_message:
        lines.append(f"{AUTHOR_ACTOR}刚刚说：{latest_message}")
    lines.append(f"请以{agent.name}的身份回应，不要超出你的立场。")
    return "\n".join(lines)
