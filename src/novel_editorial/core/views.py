"""Layered role views and on-demand retrieval for a workspace (U19)."""

from __future__ import annotations

from novel_editorial.core.chat import (
    _is_conversation_message,
    get_workspace_or_raise,
    list_messages,
)
from novel_editorial.core.draft import build_memory_pack, list_drafts
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.models import (
    Agent,
    AgentMemory,
    Decision,
    Draft,
    DraftVersion,
    Message,
    Review,
)

WRITER_VIEW = "writer"
EDITOR_VIEW = "editor"
BOSS_VIEW = "boss"

VIEW_ROLE_ALIASES: dict[str, str] = {
    "写手": WRITER_VIEW,
    "主编": EDITOR_VIEW,
    "总编": EDITOR_VIEW,
    "责编": EDITOR_VIEW,
    "作者": BOSS_VIEW,
}

VIEW_ROLE_LABELS: tuple[str, ...] = ("写手", "主编", "总编", "责编", "作者")

RECENT_CONVERSATION_LIMIT = 10
RECENT_SUMMARY_LIMIT = 5
SNIPPET_WIDTH = 40


def build_role_view(db: DB, workspace_id: str, role_alias: str) -> str:
    """Render the default layered view for one role alias."""
    view = VIEW_ROLE_ALIASES.get(role_alias)
    if view is None:
        expected = "、".join(VIEW_ROLE_LABELS)
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"invalid view role: {role_alias} (expected one of: {expected})",
        )
    get_workspace_or_raise(db, workspace_id)
    if view == WRITER_VIEW:
        return build_memory_pack(db, workspace_id)
    if view == EDITOR_VIEW:
        return build_editor_view(db, workspace_id)
    return build_boss_view(db, workspace_id)


def _profile_lines(db: DB, workspace_id: str) -> list[str]:
    workspace = get_workspace_or_raise(db, workspace_id)
    return [
        "作品档案：",
        f"标题：《{workspace.title}》",
        f"体裁：{workspace.genre}",
        f"简介：{workspace.description}",
    ]


def build_editor_view(db: DB, workspace_id: str) -> str:
    """Editor-in-chief / editor view: work profile plus recent conversation."""
    lines = _profile_lines(db, workspace_id)
    messages = [
        message for message in list_messages(db, workspace_id) if _is_conversation_message(message)
    ]
    lines.append("最近对话：")
    if not messages:
        lines.append("（暂无）")
    else:
        for message in messages[-RECENT_CONVERSATION_LIMIT:]:
            lines.append(f"[{message.role}] {message.actor}: {message.content}")
    return "\n".join(lines)


def build_boss_view(db: DB, workspace_id: str) -> str:
    """Boss (author) view: profile, band mood, drafts, and recent reviews/decisions."""
    lines = _profile_lines(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        agents = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id)
            .order_by(Agent.created_at, Agent.id)
            .all()
        )
        reviews = (
            session.query(Review)
            .filter_by(workspace_id=workspace_id)
            .order_by(Review.created_at, Review.id)
            .all()
        )
        decisions = (
            session.query(Decision)
            .filter_by(workspace_id=workspace_id)
            .order_by(Decision.created_at, Decision.id)
            .all()
        )
    lines.append("班子状态：")
    for agent in agents:
        lines.append(f"- {agent.name}（{agent.mood}）")
    lines.append("草稿：")
    drafts = list_drafts(db, workspace_id)
    if not drafts:
        lines.append("（暂无）")
    else:
        for draft in drafts:
            lines.append(f"- {draft.title} {draft.status} v{draft.current_version}")
    lines.append("最近意见：")
    if not reviews:
        lines.append("（暂无）")
    else:
        for review in reviews[-RECENT_SUMMARY_LIMIT:]:
            lines.append(f"[{review.role}] {review.actor}: {review.content}")
    lines.append("最近决策：")
    if not decisions:
        lines.append("（暂无）")
    else:
        for decision in decisions[-RECENT_SUMMARY_LIMIT:]:
            suffix = f": {decision.content}" if decision.content else ""
            lines.append(f"[{decision.action}] {decision.actor}{suffix}")
    return "\n".join(lines)


def _snippet(text: str, keyword: str, *, width: int = SNIPPET_WIDTH) -> str:
    """Trim text around the first match so each result stays readable."""
    collapsed = " ".join(text.split())
    index = collapsed.lower().find(keyword.lower())
    if index < 0:
        index = 0
    start = max(0, index - width)
    end = min(len(collapsed), index + len(keyword) + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(collapsed) else ""
    return f"{prefix}{collapsed[start:end]}{suffix}"


def search_memory(db: DB, workspace_id: str, keyword: str) -> str:
    """Case-insensitive substring search with source citations across one workspace."""
    if not keyword.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "search keyword must not be empty")
    workspace = get_workspace_or_raise(db, workspace_id)
    needle = keyword.lower()
    lines: list[str] = []

    profile_fields = (
        ("标题", workspace.title),
        ("体裁", workspace.genre),
        ("简介", workspace.description),
    )
    for label, value in profile_fields:
        if needle in value.lower():
            lines.append(
                f"[档案] {label}：{_snippet(value, keyword)}"
                f"（来源: 作品《{workspace.title}》）"
            )

    with db.workspace_session(workspace_id) as session:
        messages = (
            session.query(Message)
            .filter_by(workspace_id=workspace_id)
            .order_by(Message.created_at, Message.id)
            .all()
        )
        reviews = (
            session.query(Review)
            .filter_by(workspace_id=workspace_id)
            .order_by(Review.created_at, Review.id)
            .all()
        )
        versions = (
            session.query(DraftVersion)
            .join(Draft, Draft.id == DraftVersion.draft_id)
            .filter(Draft.workspace_id == workspace_id)
            .order_by(DraftVersion.created_at, DraftVersion.id)
            .all()
        )
        notes = (
            session.query(AgentMemory)
            .filter_by(workspace_id=workspace_id)
            .order_by(AgentMemory.created_at, AgentMemory.id)
            .all()
        )
        for message in messages:
            if needle in message.content.lower():
                lines.append(
                    f"[对话] {_snippet(message.content, keyword)}（来源: {message.actor}）"
                )
        for review in reviews:
            if needle in review.content.lower():
                lines.append(
                    f"[意见] {_snippet(review.content, keyword)}（来源: {review.actor}）"
                )
        for version in versions:
            if needle in version.content.lower():
                draft = session.get(Draft, version.draft_id)
                title = draft.title if draft is not None else ""
                lines.append(
                    f"[版本] {_snippet(version.content, keyword)}"
                    f"（来源: {title} v{version.version}）"
                )
        for note in notes:
            if needle in note.content.lower():
                owner = session.get(Agent, note.agent_id)
                owner_name = owner.name if owner is not None else note.agent_id
                lines.append(
                    f"[笔记] {_snippet(note.content, keyword)}（来源: {owner_name}）"
                )

    if not lines:
        return "no matches"
    return "\n".join(lines)
