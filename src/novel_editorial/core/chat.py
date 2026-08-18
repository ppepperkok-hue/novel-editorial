"""Conversation services for the editorial band."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.plot import plot_threads_section
from novel_editorial.events import EventType
from novel_editorial.store.db import DB
from novel_editorial.store.events import record_event_in_session
from novel_editorial.store.models import Agent, AgentRole, Message, Workspace

AUTHOR_ACTOR = "作者"
PROACTIVE_PAYLOAD = {"initiator": "agent", "kind": "proactive_question"}
PROACTIVE_QUESTION = (
    "我想先确认一下：这部作品的主角动机和核心冲突，咱们还没对齐吧？"
    "这个定不下来，后面每一章都会飘。"
)

MOOD_TALK = "投入对话"
MOOD_REVISING = "专注修订"
MOOD_REJECTED = "低落"
MOOD_ACCEPTED = "振奋"

ROLE_ALIASES: dict[str, str] = {
    "总编": AgentRole.EDITOR_IN_CHIEF,
    "主编": AgentRole.EDITOR_IN_CHIEF,
    "责编": AgentRole.EDITOR,
    "写手": AgentRole.WRITER,
    "审稿": AgentRole.REVIEWER,
}

NEGATION_PREFIXES = ("不", "别", "勿", "莫", "不必")

OVERRIDE_PHRASES: tuple[str, ...] = (
    "以老板身份",
    "我拍板",
    "老板拍板",
    "就这么定了",
    "我定了",
    "老板说了算",
    "听我的",
)


@dataclass(frozen=True)
class RefusalRule:
    """One deterministic stance rule with stable, traceable identifiers.

    ``rule`` is the stable rule id carried by refusal/override payloads;
    ``stance`` is the stance summary shown alongside the refusal so the
    judgment stays traceable to the partner's stance/values fields.
    """

    rule: str
    stance: str
    keywords: tuple[str, ...]
    refusal: str
    reaffirmation: str
    acceptance: str


REFUSAL_RULES: dict[str, list[RefusalRule]] = {
    AgentRole.WRITER: [
        RefusalRule(
            rule="writer_portrayal",
            stance="忠于人物内心，反对为剧情强行降智",
            keywords=("违背人设", "强行降智", "无视设定", "乱改设定"),
            refusal=("这个我写不了。违背人物逻辑的剧情，写出来也是假的，我的立场不允许。"),
            reaffirmation=(
                "我还是这句话，写不了。违背人物逻辑的内容我坚持不写，换个不塌人设的写法再说。"
            ),
            acceptance=("明白了，作者拍板。这条我按你的意思来，立场我先记着，写完有问题我再提。"),
        ),
    ],
    AgentRole.REVIEWER: [
        RefusalRule(
            rule="reviewer_consistency",
            stance="连贯性与一致性优先，前后矛盾必须退稿",
            keywords=("放行", "忽略矛盾", "别管矛盾", "忽略逻辑", "别查伏笔", "直接过", "别较真"),
            refusal=("这个我不能放行。前后矛盾不修就过稿，等于砸审稿的招牌。"),
            reaffirmation=("我还是不能放行。前后矛盾这条线我坚持，你换别的指令我照做，过稿不行。"),
            acceptance=("行，作者拍板。矛盾这条我先放行，标记我留着，后面咬合不上我再提。"),
        ),
    ],
    AgentRole.EDITOR: [
        RefusalRule(
            rule="editor_hooks",
            stance="读者节奏优先，钩子与信息密度优先",
            keywords=("删掉钩子", "删钩子", "钩子全删", "不要钩子", "平铺直叙", "不要节奏"),
            refusal=("钩子删光、节奏放平，读者留不住。这稿我不接，先改回来再说。"),
            reaffirmation=("钩子这条我还是坚持：删光、放平，读者留不住。我的立场没变，先改回来。"),
            acceptance=("行，老板说了算。钩子先照你说的改，节奏我盯着，别崩太远。"),
        ),
    ],
}


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


def check_refusal(agent: Agent, message: str) -> RefusalRule | None:
    """Return the stance rule the message conflicts with, or None.

    The judgment stays deterministic: a rule fires only when one of its
    keywords appears without a negation prefix. The returned rule carries the
    stable ``rule`` id and ``stance`` summary used by refusal payloads.
    """
    for rule in REFUSAL_RULES.get(agent.role, []):
        if any(_keyword_triggered(message, keyword) for keyword in rule.keywords):
            return rule
    return None


def is_author_override(message: str) -> bool:
    """True when the author explicitly overrides a partner's stance."""
    return any(_keyword_triggered(message, phrase) for phrase in OVERRIDE_PHRASES)


def _has_rule_record(db: DB, workspace_id: str, agent: Agent, kind: str, rule: str) -> bool:
    """True when one partner already recorded ``kind`` for ``rule`` here.

    Matching happens entirely in SQLite. Each ``json_extract`` runs inside a
    CASE guarded by ``json_valid``, so malformed payloads evaluate to NULL
    without ever reaching ``json_extract`` (which raises on them), regardless
    of how SQLite orders the WHERE terms. The extracted kind/rule fields are
    compared exactly, independent of JSON serialization style (pretty or
    compact), and cannot be fooled by LIKE wildcards, rule ids that share a
    prefix, or extra fields.
    """
    kind_match = case(
        (func.json_valid(Message.payload), func.json_extract(Message.payload, "$.kind")),
        else_=None,
    )
    rule_match = case(
        (func.json_valid(Message.payload), func.json_extract(Message.payload, "$.rule")),
        else_=None,
    )
    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(Message)
            .filter(
                Message.workspace_id == workspace_id,
                Message.role == "agent",
                Message.actor == agent.name,
                kind_match == kind,
                rule_match == rule,
            )
            .first()
        )
    return row is not None


def has_same_rule_refusal(db: DB, workspace_id: str, agent: Agent, rule: str) -> bool:
    """True when this partner already refused the same rule in this workspace.

    Refusal history spans both chat refusals (kind=refusal) and delegation
    refusals (kind=delegation_response carrying the rule), so a repeated rule
    hit reaffirms the stance regardless of the channel it came from. Accepted
    delegation responses carry no rule field and never match here.
    """
    return _has_rule_record(
        db, workspace_id, agent, "refusal", rule
    ) or _has_rule_record(db, workspace_id, agent, "delegation_response", rule)


def has_same_rule_override(db: DB, workspace_id: str, agent: Agent, rule: str) -> bool:
    """True when the author already overrode this partner's stance rule here."""
    return _has_rule_record(db, workspace_id, agent, "override", rule)


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


def _record_message_in_session(
    session: Session,
    workspace_id: str,
    *,
    role: str,
    actor: str,
    content: str,
    payload: dict | None = None,
) -> Message:
    """Add one message inside an open session; the caller owns the commit."""
    message = Message(
        workspace_id=workspace_id,
        role=role,
        actor=actor,
        content=content,
        payload=json.dumps(payload or {}, ensure_ascii=False),
    )
    session.add(message)
    if role == "agent":
        record_event_in_session(
            session,
            workspace_id,
            type=EventType.AGENT_MESSAGE,
            actor=actor,
            payload=payload or {},
        )
    return message


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
        message = _record_message_in_session(
            session,
            workspace_id=workspace_id,
            role=role,
            actor=actor,
            content=content,
            payload=payload,
        )
        session.commit()
        return message


def _update_agent_mood_in_session(
    session: Session,
    workspace_id: str,
    agent_id: str,
    mood: str,
) -> Message | None:
    """Apply one mood change inside an open session; returns the trace or None if unchanged."""
    if not mood:
        raise NovelError(ErrorCode.USAGE_ERROR, "mood must not be empty")
    row = (
        session.query(Agent)
        .filter_by(workspace_id=workspace_id, id=agent_id)
        .first()
    )
    if row is None:
        raise NovelError(ErrorCode.NOT_FOUND, f"agent not found: {agent_id}")
    previous = row.mood
    if previous == mood:
        return None
    row.mood = mood
    return _record_message_in_session(
        session,
        workspace_id,
        role="system",
        actor=row.name,
        content=f"{row.name} 的状态从「{previous}」变为「{mood}」",
        payload={"kind": "mood_change", "from": previous, "to": mood, "agent": row.name},
    )


def update_agent_mood(db: DB, workspace_id: str, agent: Agent, mood: str) -> Message | None:
    """Persist one partner's mood change and its trace in a single transaction."""
    with db.workspace_session(workspace_id) as session:
        trace = _update_agent_mood_in_session(session, workspace_id, agent.id, mood)
        session.commit()
        return trace


def list_messages(db: DB, workspace_id: str) -> list[Message]:
    with db.workspace_session(workspace_id) as session:
        return session.query(Message).order_by(Message.created_at).all()


def has_proactive_message(db: DB, workspace_id: str) -> bool:
    """True only for talk's first-round question (kind marker without a trigger).

    Draft follow-ups reuse the ``proactive_question`` kind but carry a ``trigger``
    key, so they must not suppress the editor's first-round question in talk.
    """
    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(Message)
            .filter(
                Message.workspace_id == workspace_id,
                Message.payload.like('%"kind": "proactive_question"%'),
                Message.payload.not_like('%"trigger"%'),
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


def _is_conversation_message(message: Message) -> bool:
    """Keep real dialogue for the prompt; system status traces are not conversation."""
    if message.role == "system":
        return False
    try:
        payload = json.loads(message.payload or "{}")
    except json.JSONDecodeError:
        payload = {}
    return payload.get("kind") != "mood_change"


def build_agent_prompt(
    workspace: Workspace,
    agent: Agent,
    history: list[Message],
    latest_message: str | None = None,
    *,
    db: DB | None = None,
    workspace_id: str | None = None,
) -> str:
    lines = [
        f"你是作品《{workspace.title}》的{agent.name}（{agent.role}）。",
        f"你的性格：{agent.personality}",
        f"你的立场：{agent.stance}",
        f"你的价值观：{agent.values}",
        f"你的审美：{agent.aesthetic}",
        f"你的工作习惯：{agent.work_habits}",
        f"作品简介：{workspace.title}（{workspace.genre}）{workspace.description}".rstrip(),
    ]
    if agent.role == AgentRole.REVIEWER and db is not None:
        section = plot_threads_section(db, workspace_id or workspace.id)
        if section:
            lines.append(section)
    lines.append("最近对话：")
    conversation = [message for message in history if _is_conversation_message(message)]
    for message in conversation[-6:]:
        lines.append(f"{message.actor}: {message.content}")
    if latest_message:
        lines.append(f"{AUTHOR_ACTOR}刚刚说：{latest_message}")
    lines.append(f"请以{agent.name}的身份回应，不要超出你的立场。")
    return "\n".join(lines)
