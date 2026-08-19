"""Layered role views and on-demand retrieval for a workspace (U19)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, and_, bindparam, func, or_, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Subquery

from novel_editorial.core.chat import (
    _is_conversation_message,
    get_workspace_or_raise,
    list_messages,
)
from novel_editorial.core.config import load_settings
from novel_editorial.core.draft import build_memory_pack, list_drafts
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.memory import effective_strength, rehearse_memory_note
from novel_editorial.core.plot import KIND_LABELS
from novel_editorial.core.setting import KIND_LABELS as SETTING_KIND_LABELS
from novel_editorial.core.setting import settings_section
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
    SettingEntry,
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
    setting_block = settings_section(db, workspace_id)
    if setting_block:
        lines.append(setting_block)
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


def _fts5_available(session: Session) -> bool:
    """Return True only when this process can create an FTS5 trigram table.

    `PRAGMA compile_options` only reflects build-time flags: an FTS5 module
    supplied by a loadable extension has no ENABLE_FTS5 entry, and a compiled
    flag can still fail to register at runtime. Creating a real temp virtual
    table is the one probe that reflects whether MATCH works right now, so the
    probe is deliberately not cached (a search probes once, costing milliseconds).

    pysqlite's legacy transaction control executes DDL outside the implicit
    transaction (driver-level autocommit), so a probe interrupted between
    CREATE and DROP leaves the temp table behind on this connection, where
    it persists after the connection returns to the pool. The DROP TABLE
    IF EXISTS below clears that residue before probing, keeping the probe
    self-healing.
    """
    try:
        session.execute(text("DROP TABLE IF EXISTS temp._novel_fts5_probe"))
        session.execute(
            text(
                "CREATE VIRTUAL TABLE temp._novel_fts5_probe "
                "USING fts5(content, tokenize='trigram')"
            )
        )
    except OperationalError:
        return False
    # Best-effort cleanup: a failed DROP is housekeeping, not a verdict, so it
    # must not crash the probe or flip True to False. Any residue is cleared
    # by the DROP IF EXISTS above on the next probe.
    try:
        session.execute(text("DROP TABLE temp._novel_fts5_probe"))
    except OperationalError as exc:
        print(
            f"warning: could not drop temp FTS5 probe table ({exc}); "
            "the next probe clears the residue with DROP TABLE IF EXISTS",
            file=sys.stderr,
        )
    return True


def _fts_tables_present(session: Session) -> bool:
    """Return True only when FTS5 MATCH works here and every shadow table exists.

    A database created on an FTS5 build keeps its shadow tables when copied
    onto a build without FTS5, where MATCH fails with "no such module: fts5".
    The runtime probe fails closed first, so every search falls back to LIKE
    instead of crashing; any missing layer also falls back as a whole.
    """
    if not _fts5_available(session):
        return False
    names = {
        name
        for name in session.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table'")
        ).scalars()
    }
    return all(name in names for name in FTS_TABLE_BY_LAYER.values())


def _fts_match_subquery(keyword: str, fts_table: str) -> Subquery:
    """Render one FTS5 MATCH subquery exposing the matching source-row ids."""
    statement = (
        text(f"SELECT id FROM {fts_table} WHERE {fts_table} MATCH :phrase")
        .bindparams(bindparam("phrase", value=_fts_phrase(keyword)))
        .columns(id=String(32))
    )
    return statement.subquery()


def _content_filter(hits: Subquery | None, content_column: Any, needle: str) -> Any:
    """Content predicate for one searchable layer.

    With FTS5 the predicate requires join membership (id present in the MATCH
    subquery) on top of the same `_like_contains` refine used by the LIKE
    path. FTS5 trigram folding is Unicode-aware while SQLite `lower()` only
    folds ASCII, so MATCH can over-match (café hits CAFÉ); the refine prunes
    those rows and keeps both paths byte-identical.
    """
    if hits is None:
        return _like_contains(content_column, needle)
    return and_(hits.c.id.is_not(None), _like_contains(content_column, needle))


def _rehearse_note_safely(db: DB, workspace_id: str, note: AgentMemory, now: datetime) -> None:
    """Rehearse one hit note; a failure must never break the search result."""
    try:
        rehearse_memory_note(db, workspace_id, note.id, now=now)
    except Exception as exc:  # noqa: BLE001 - search must survive any rehearsal failure
        print(
            f"warning: memory rehearsal failed for note {note.id}: {exc}",
            file=sys.stderr,
        )


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
        if use_fts and not _fts_tables_present(session):
            use_fts = False

        message_hits = (
            _fts_match_subquery(keyword, FTS_TABLE_BY_LAYER["message"]) if use_fts else None
        )
        review_hits = (
            _fts_match_subquery(keyword, FTS_TABLE_BY_LAYER["review"]) if use_fts else None
        )
        version_hits = (
            _fts_match_subquery(keyword, FTS_TABLE_BY_LAYER["draft_version"])
            if use_fts
            else None
        )
        note_hits = (
            _fts_match_subquery(keyword, FTS_TABLE_BY_LAYER["agent_memory"]) if use_fts else None
        )
        message_content = _content_filter(message_hits, Message.content, needle)
        review_content = _content_filter(review_hits, Review.content, needle)
        version_content = _content_filter(version_hits, DraftVersion.content, needle)
        note_content = _content_filter(note_hits, AgentMemory.content, needle)

        messages_query = session.query(Message).filter_by(workspace_id=workspace_id)
        if message_hits is not None:
            messages_query = messages_query.outerjoin(
                message_hits, message_hits.c.id == Message.id
            )
        messages = (
            messages_query.filter(message_content)
            .order_by(Message.created_at, Message.id)
            .all()
        )
        reviews_query = session.query(Review).filter_by(workspace_id=workspace_id)
        if review_hits is not None:
            reviews_query = reviews_query.outerjoin(review_hits, review_hits.c.id == Review.id)
        reviews = (
            reviews_query.filter(review_content)
            .order_by(Review.created_at, Review.id)
            .all()
        )
        versions_query = session.query(DraftVersion).join(
            Draft, Draft.id == DraftVersion.draft_id
        )
        if version_hits is not None:
            versions_query = versions_query.outerjoin(
                version_hits, version_hits.c.id == DraftVersion.id
            )
        versions = (
            versions_query.filter(
                Draft.workspace_id == workspace_id,
                version_content,
            )
            .order_by(DraftVersion.created_at, DraftVersion.id)
            .all()
        )
        notes_query = (
            session.query(AgentMemory)
            .filter_by(workspace_id=workspace_id)
            .filter(AgentMemory.archived_at.is_(None))
        )
        if note_hits is not None:
            notes_query = notes_query.outerjoin(note_hits, note_hits.c.id == AgentMemory.id)
        notes = notes_query.filter(note_content).all()
        now = datetime.now(UTC)
        decay_per_day = load_settings().memory_decay_per_day
        notes.sort(
            key=lambda note: (
                -effective_strength(note, now, decay_per_day=decay_per_day),
                note.created_at,
                note.id,
            )
        )
        for note in notes:
            _rehearse_note_safely(db, workspace_id, note, now)
        setting_entries = (
            session.query(SettingEntry)
            .filter_by(workspace_id=workspace_id)
            .filter(
                or_(
                    _like_contains(SettingEntry.name, needle),
                    _like_contains(SettingEntry.content, needle),
                )
            )
            .order_by(SettingEntry.updated_at, SettingEntry.id)
            .all()
        )
        for entry in setting_entries:
            label = SETTING_KIND_LABELS.get(entry.kind, entry.kind)
            lines.append(
                f"[设定] {label}：{entry.name}——{_snippet(entry.content, keyword)}"
                f"（来源: {entry.source} v{entry.current_version}）"
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
        if use_fts and not _fts_tables_present(session):
            use_fts = False

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

        message_hits = (
            _fts_match_subquery(keyword, FTS_TABLE_BY_LAYER["message"]) if use_fts else None
        )
        review_hits = (
            _fts_match_subquery(keyword, FTS_TABLE_BY_LAYER["review"]) if use_fts else None
        )
        version_hits = (
            _fts_match_subquery(keyword, FTS_TABLE_BY_LAYER["draft_version"])
            if use_fts
            else None
        )
        note_hits = (
            _fts_match_subquery(keyword, FTS_TABLE_BY_LAYER["agent_memory"]) if use_fts else None
        )
        thread_hits = (
            _fts_match_subquery(keyword, FTS_TABLE_BY_LAYER["plot_thread"]) if use_fts else None
        )
        message_content = _content_filter(message_hits, Message.content, needle)
        review_content = _content_filter(review_hits, Review.content, needle)
        version_content = _content_filter(version_hits, DraftVersion.content, needle)
        note_content = _content_filter(note_hits, AgentMemory.content, needle)
        thread_content = _content_filter(thread_hits, PlotThread.content, needle)

        messages_query = session.query(Message).filter_by(workspace_id=workspace_id)
        if message_hits is not None:
            messages_query = messages_query.outerjoin(
                message_hits, message_hits.c.id == Message.id
            )
        messages = (
            messages_query.filter(
                or_(
                    message_content,
                    _like_contains(Message.actor, needle),
                )
            )
            .order_by(Message.created_at, Message.id)
            .all()
        )
        reviews_query = session.query(Review).filter_by(workspace_id=workspace_id)
        if review_hits is not None:
            reviews_query = reviews_query.outerjoin(review_hits, review_hits.c.id == Review.id)
        reviews = (
            reviews_query.filter(
                or_(
                    review_content,
                    _like_contains(Review.actor, needle),
                )
            )
            .order_by(Review.created_at, Review.id)
            .all()
        )
        versions_query = session.query(DraftVersion).join(
            Draft, Draft.id == DraftVersion.draft_id
        )
        if version_hits is not None:
            versions_query = versions_query.outerjoin(
                version_hits, version_hits.c.id == DraftVersion.id
            )
        versions = (
            versions_query.filter(
                Draft.workspace_id == workspace_id,
                or_(
                    version_content,
                    _like_contains(Draft.title, needle),
                ),
            )
            .order_by(DraftVersion.created_at, DraftVersion.id)
            .all()
        )
        notes_query = (
            session.query(AgentMemory, Agent.name)
            .outerjoin(
                Agent,
                (Agent.id == AgentMemory.agent_id)
                & (Agent.workspace_id == AgentMemory.workspace_id),
            )
            .filter(AgentMemory.archived_at.is_(None))
        )
        if note_hits is not None:
            notes_query = notes_query.outerjoin(note_hits, note_hits.c.id == AgentMemory.id)
        notes = (
            notes_query.filter(
                AgentMemory.workspace_id == workspace_id,
                or_(
                    note_content,
                    _like_contains(func.coalesce(Agent.name, AgentMemory.agent_id), needle),
                ),
            )
            .all()
        )
        now = datetime.now(UTC)
        decay_per_day = load_settings().memory_decay_per_day
        notes.sort(
            key=lambda pair: (
                -effective_strength(pair[0], now, decay_per_day=decay_per_day),
                pair[0].created_at,
                pair[0].id,
            )
        )
        for note, _agent_name in notes:
            _rehearse_note_safely(db, workspace_id, note, now)
        setting_entries = (
            session.query(SettingEntry)
            .filter_by(workspace_id=workspace_id)
            .filter(
                or_(
                    _like_contains(SettingEntry.name, needle),
                    _like_contains(SettingEntry.content, needle),
                )
            )
            .order_by(SettingEntry.updated_at, SettingEntry.id)
            .all()
        )
        for entry in setting_entries:
            label = SETTING_KIND_LABELS.get(entry.kind, entry.kind)
            lines.append(
                f"[设定] {label}：{entry.name}——{_snippet(entry.content, keyword)}"
                f"（来源: {entry.source} v{entry.current_version}）"
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
        threads_query = session.query(PlotThread).filter_by(workspace_id=workspace_id)
        if thread_hits is not None:
            threads_query = threads_query.outerjoin(
                thread_hits, thread_hits.c.id == PlotThread.id
            )
        threads = (
            threads_query.filter(
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
