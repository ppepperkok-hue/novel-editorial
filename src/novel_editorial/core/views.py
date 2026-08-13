"""Layered role views and on-demand retrieval for a workspace (U19)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from novel_editorial.core.chat import (
    _is_conversation_message,
    get_workspace_or_raise,
    list_messages,
)
from novel_editorial.core.draft import build_memory_pack, list_drafts
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.plot import KIND_LABELS
from novel_editorial.store.db import DB
from novel_editorial.store.models import (
    Agent,
    AgentMemory,
    Decision,
    Draft,
    DraftVersion,
    Message,
    PlotThread,
    Review,
    StyleAnchor,
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


def _like_contains(column: Any, needle: str) -> Any:
    """Case-insensitive literal substring predicate pushed down to SQL LIKE.

    Callers pass an already-lowercased needle. `%`, `_`, and `\\` inside the
    needle are escaped so LIKE keeps the exact literal substring semantics of
    Python's `needle in value.lower()`.
    """
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return func.lower(column).like(f"%{escaped}%", escape="\\")


FTS_MIN_CHARS = 3

# FTS5 trigram shadow tables created by migration 9c3a71b5d2e4. Table names
# come from this mapping (never from user input), so interpolating them into
# the MATCH statement below is safe.
FTS_TABLE_BY_LAYER: dict[str, str] = {
    "message": "message_fts",
    "review": "review_fts",
    "draft_version": "draft_version_fts",
    "agent_memory": "agent_memory_fts",
    "plot_thread": "plot_thread_fts",
}


def _fts_phrase(keyword: str) -> str:
    """Render a keyword as one FTS5 phrase with embedded double-quotes escaped.

    FTS5 phrase syntax doubles a `"` inside the phrase, so a keyword like
    `a"b` stays a single literal substring instead of closing the phrase early
    or injecting FTS5 query syntax.
    """
    return '"' + keyword.replace('"', '""') + '"'


def _content_hit_ids(session: Session, fts_table: str, keyword: str) -> list[str]:
    """Return source-row ids whose content matches the keyword in the FTS index."""
    statement = text(f"SELECT id FROM {fts_table} WHERE {fts_table} MATCH :phrase")
    return list(session.execute(statement, {"phrase": _fts_phrase(keyword)}).scalars())


def search_memory(
    db: DB,
    workspace_id: str,
    keyword: str,
    *,
    _force_fts: bool | None = None,
) -> str:
    """Case-insensitive substring search with source citations across one workspace."""
    if not keyword.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "search keyword must not be empty")
    workspace = get_workspace_or_raise(db, workspace_id)
    needle = keyword.lower()
    use_fts = _force_fts if _force_fts is not None else len(keyword) >= FTS_MIN_CHARS
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
        if use_fts:
            message_content = Message.id.in_(
                _content_hit_ids(session, FTS_TABLE_BY_LAYER["message"], keyword)
            )
            review_content = Review.id.in_(
                _content_hit_ids(session, FTS_TABLE_BY_LAYER["review"], keyword)
            )
            version_content = DraftVersion.id.in_(
                _content_hit_ids(session, FTS_TABLE_BY_LAYER["draft_version"], keyword)
            )
            note_content = AgentMemory.id.in_(
                _content_hit_ids(session, FTS_TABLE_BY_LAYER["agent_memory"], keyword)
            )
        else:
            message_content = _like_contains(Message.content, needle)
            review_content = _like_contains(Review.content, needle)
            version_content = _like_contains(DraftVersion.content, needle)
            note_content = _like_contains(AgentMemory.content, needle)

        messages = (
            session.query(Message)
            .filter_by(workspace_id=workspace_id)
            .filter(message_content)
            .order_by(Message.created_at, Message.id)
            .all()
        )
        reviews = (
            session.query(Review)
            .filter_by(workspace_id=workspace_id)
            .filter(review_content)
            .order_by(Review.created_at, Review.id)
            .all()
        )
        versions = (
            session.query(DraftVersion)
            .join(Draft, Draft.id == DraftVersion.draft_id)
            .filter(
                Draft.workspace_id == workspace_id,
                version_content,
            )
            .order_by(DraftVersion.created_at, DraftVersion.id)
            .all()
        )
        notes = (
            session.query(AgentMemory)
            .filter_by(workspace_id=workspace_id)
            .filter(note_content)
            .order_by(AgentMemory.created_at, AgentMemory.id)
            .all()
        )
        for message in messages:
            lines.append(
                f"[对话] {_snippet(message.content, keyword)}（来源: {message.actor}）"
            )
        for review in reviews:
            lines.append(
                f"[意见] {_snippet(review.content, keyword)}（来源: {review.actor}）"
            )
        for version in versions:
            draft = session.get(Draft, version.draft_id)
            title = draft.title if draft is not None else ""
            lines.append(
                f"[版本] {_snippet(version.content, keyword)}"
                f"（来源: {title} v{version.version}）"
            )
        for note in notes:
            owner = session.get(Agent, note.agent_id)
            owner_name = owner.name if owner is not None else note.agent_id
            lines.append(
                f"[笔记] {_snippet(note.content, keyword)}（来源: {owner_name}）"
            )

    if not lines:
        return "no matches"
    return "\n".join(lines)


def search_all_layers(
    db: DB,
    workspace_id: str,
    keyword: str,
    *,
    _force_fts: bool | None = None,
) -> str:
    """Case-insensitive search across every visible layer of one workspace (F18).

    Extends `search_memory` with style anchors, decisions, and plot threads while
    keeping the same snippet and `[layer] 片段（来源: ...）` citation format.
    """
    if not keyword.strip():
        raise NovelError(ErrorCode.USAGE_ERROR, "search keyword must not be empty")
    keyword = keyword.strip()
    workspace = get_workspace_or_raise(db, workspace_id)
    needle = keyword.lower()
    use_fts = _force_fts if _force_fts is not None else len(keyword) >= FTS_MIN_CHARS
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
        anchor = session.query(StyleAnchor).filter_by(workspace_id=workspace_id).first()
        anchor_fields = (
            ("描述", anchor.description if anchor is not None else ""),
            ("禁忌词", anchor.forbidden_words if anchor is not None else ""),
        )
        for label, value in anchor_fields:
            if needle in value.lower():
                lines.append(
                    f"[风格] {label}：{_snippet(value, keyword)}（来源: 风格锚点）"
                )

        if use_fts:
            message_content = Message.id.in_(
                _content_hit_ids(session, FTS_TABLE_BY_LAYER["message"], keyword)
            )
            review_content = Review.id.in_(
                _content_hit_ids(session, FTS_TABLE_BY_LAYER["review"], keyword)
            )
            version_content = DraftVersion.id.in_(
                _content_hit_ids(session, FTS_TABLE_BY_LAYER["draft_version"], keyword)
            )
            note_content = AgentMemory.id.in_(
                _content_hit_ids(session, FTS_TABLE_BY_LAYER["agent_memory"], keyword)
            )
            thread_content = PlotThread.id.in_(
                _content_hit_ids(session, FTS_TABLE_BY_LAYER["plot_thread"], keyword)
            )
        else:
            message_content = _like_contains(Message.content, needle)
            review_content = _like_contains(Review.content, needle)
            version_content = _like_contains(DraftVersion.content, needle)
            note_content = _like_contains(AgentMemory.content, needle)
            thread_content = _like_contains(PlotThread.content, needle)

        messages = (
            session.query(Message)
            .filter_by(workspace_id=workspace_id)
            .filter(
                or_(
                    message_content,
                    _like_contains(Message.actor, needle),
                )
            )
            .order_by(Message.created_at, Message.id)
            .all()
        )
        reviews = (
            session.query(Review)
            .filter_by(workspace_id=workspace_id)
            .filter(
                or_(
                    review_content,
                    _like_contains(Review.actor, needle),
                )
            )
            .order_by(Review.created_at, Review.id)
            .all()
        )
        versions = (
            session.query(DraftVersion)
            .join(Draft, Draft.id == DraftVersion.draft_id)
            .filter(
                Draft.workspace_id == workspace_id,
                or_(
                    version_content,
                    _like_contains(Draft.title, needle),
                ),
            )
            .order_by(DraftVersion.created_at, DraftVersion.id)
            .all()
        )
        notes = (
            session.query(AgentMemory, Agent.name)
            .outerjoin(
                Agent,
                (Agent.id == AgentMemory.agent_id)
                & (Agent.workspace_id == AgentMemory.workspace_id),
            )
            .filter(
                AgentMemory.workspace_id == workspace_id,
                or_(
                    note_content,
                    _like_contains(func.coalesce(Agent.name, AgentMemory.agent_id), needle),
                ),
            )
            .order_by(AgentMemory.created_at, AgentMemory.id)
            .all()
        )
        decisions = (
            session.query(Decision)
            .filter_by(workspace_id=workspace_id)
            .filter(
                or_(
                    _like_contains(Decision.action, needle),
                    _like_contains(Decision.actor, needle),
                    _like_contains(Decision.content, needle),
                )
            )
            .order_by(Decision.created_at, Decision.id)
            .all()
        )
        threads = (
            session.query(PlotThread)
            .filter_by(workspace_id=workspace_id)
            .filter(
                or_(
                    thread_content,
                    _like_contains(PlotThread.kind, needle),
                    _like_contains(PlotThread.status, needle),
                )
            )
            .order_by(PlotThread.created_at, PlotThread.id)
            .all()
        )

        for message in messages:
            actor_hit = needle in message.actor.lower()
            prefix = f"{message.actor}：" if actor_hit else ""
            lines.append(
                f"[对话] {prefix}{_snippet(message.content, keyword)}（来源: {message.actor}）"
            )
        for review in reviews:
            actor_hit = needle in review.actor.lower()
            prefix = f"{review.actor}：" if actor_hit else ""
            lines.append(
                f"[意见] {prefix}{_snippet(review.content, keyword)}（来源: {review.actor}）"
            )
        draft_titles = {
            draft.id: draft.title
            for draft in session.query(Draft).filter_by(workspace_id=workspace_id).all()
        }
        for version in versions:
            title = draft_titles.get(version.draft_id, "")
            title_hit = needle in title.lower()
            prefix = f"{title}：" if title_hit else ""
            lines.append(
                f"[版本] {prefix}{_snippet(version.content, keyword)}"
                f"（来源: {title} v{version.version}）"
            )
        for note, agent_name in notes:
            owner_name = agent_name if agent_name is not None else note.agent_id
            owner_hit = needle in owner_name.lower()
            prefix = f"{owner_name}：" if owner_hit else ""
            lines.append(
                f"[笔记] {prefix}{_snippet(note.content, keyword)}（来源: {owner_name}）"
            )
        for decision in decisions:
            display = decision.content or decision.action
            lines.append(
                f"[决策] {_snippet(display, keyword)}"
                f"（来源: 决策 {decision.action}（{decision.actor}））"
            )
        for thread in threads:
            kind_hit = needle in thread.kind.lower()
            status_hit = needle in thread.status.lower()
            label = KIND_LABELS.get(thread.kind, thread.kind)
            prefix = f"{thread.kind}/{thread.status}：" if kind_hit or status_hit else ""
            lines.append(
                f"[线索] {prefix}{_snippet(thread.content, keyword)}"
                f"（来源: 线索 {label}（{thread.status}））"
            )

    if not lines:
        return "no matches"
    return "\n".join(lines)
