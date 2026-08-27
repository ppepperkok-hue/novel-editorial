"""FastAPI application: the HTTP door to the same editorial capabilities as the CLI."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask

from novel_editorial.core import (
    decision,
    draft,
    inspiration,
    log,
    outline,
    overview,
    proactive,
    review,
    setting,
    structure,
    style,
    templates,
    views,
    workspace,
)
from novel_editorial.core.agents import resolve_agent
from novel_editorial.core.archive import (
    export_workspace_archive,
    import_workspace_archive,
)
from novel_editorial.core.behavior import (
    BEHAVIOR_KINDS,
    current_behavior_state,
    list_behavior_timeline,
    record_behavior_entry_safe,
)
from novel_editorial.core.calibration import scan_corpus
from novel_editorial.core.chat import (
    AUTHOR_ACTOR,
    MOOD_ACCEPTED,
    MOOD_TALK,
    PROACTIVE_PAYLOAD,
    PROACTIVE_QUESTION,
    build_agent_prompt,
    check_refusal,
    get_agent,
    get_workspace_or_raise,
    has_proactive_message,
    has_same_rule_override,
    has_same_rule_refusal,
    is_author_override,
    list_messages,
    record_message,
    resolve_target_role,
    update_agent_mood,
)
from novel_editorial.core.config import (
    Settings,
    load_settings,
    set_config_value,
    set_quality_threshold,
)
from novel_editorial.core.consistency import check_consistency
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.feedback import analyze_feedback, load_feedback_samples
from novel_editorial.core.motives import clear_motive, list_motives
from novel_editorial.core.natural_discussion import check_summon_trigger_safe
from novel_editorial.core.patience import STATE_KEYS, patience_pools
from novel_editorial.core.style import (
    extract_style_keywords,
    find_style_anchor,
    get_style_anchor,
)
from novel_editorial.core.style_drift import compute_style_drift, read_forbidden_words
from novel_editorial.core.style_learn import (
    build_suggested_description,
    collect_corpus_texts,
    compute_style_profile,
)
from novel_editorial.llm.client import LLMMessage, build_client
from novel_editorial.quality.explain import (
    explain_quality,
    render_explanation,
    style_consistency_summary,
)
from novel_editorial.quality.gate import check_quality
from novel_editorial.quality.gems import (
    SIGNAL_DIALOGUE,
    SIGNAL_NUMBER_DETAIL,
    SIGNAL_SENSORY,
    GoodSentence,
    find_good_sentences,
)
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events, list_events_since
from novel_editorial.store.models import (
    Agent,
    AgentRole,
    BehaviorTimeline,
    Decision,
    Draft,
    DraftVersion,
    Event,
    Inspiration,
    Message,
    Outline,
    SettingEntry,
    StyleAnchor,
    Workspace,
    WorkspaceStructureNode,
)

_WORKSPACE_FIELDS = (
    "id",
    "title",
    "genre",
    "description",
    "status",
    "created_at",
)
_AGENT_FIELDS = (
    "id",
    "name",
    "role",
    "personality",
    "stance",
    "values",
    "aesthetic",
    "emotion_baseline",
    "mood",
    "work_habits",
    "weaknesses",
    "relationship_presets",
    "private_motive",
    "created_at",
)

#: Poll interval for new events inside an open SSE stream (seconds).
SSE_POLL_SECONDS = 1.0
#: Heartbeat comment interval for the SSE stream (seconds), per FE-W1 S1.
SSE_HEARTBEAT_SECONDS = 15


class CreateWorkspaceBody(BaseModel):
    title: str = Field(min_length=1)
    genre: str = ""
    description: str = ""


class DecisionBody(BaseModel):
    draft_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    content: str = ""


class TalkSendBody(BaseModel):
    message: str = Field(min_length=1)

    @field_validator("message")
    @classmethod
    def _message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty or whitespace-only")
        return value


class DraftGenerateBody(BaseModel):
    title: str = "未命名章节"
    writer: str | None = None


class DraftReviseBody(BaseModel):
    reason: str = "revision"
    writer: str | None = None


class DraftNewBody(BaseModel):
    title: str = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be empty or whitespace-only")
        return value


class DraftSaveBody(BaseModel):
    content: str = Field(min_length=1)
    reason: str = "作者修改"

    @field_validator("content")
    @classmethod
    def _content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be empty or whitespace-only")
        return value


class ReviewAddBody(BaseModel):
    draft_id: str = Field(min_length=1)
    source: str = "作者"
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def _content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be empty or whitespace-only")
        return value


class StyleSetBody(BaseModel):
    description: str = ""
    forbidden: str = ""


class StructureAddBody(BaseModel):
    kind: str
    title: str
    parent: str | None = None
    draft: str | None = None
    order: int | None = None


class StructurePatchBody(BaseModel):
    title: str | None = None
    status: str | None = None


class StructureMoveBody(BaseModel):
    parent: str | None = None
    root: bool = False
    order: int | None = None


class OutlineWriteBody(BaseModel):
    content: str
    reason: str | None = None
    actor: str = "作者"


class SettingWriteBody(BaseModel):
    kind: str | None = None
    name: str | None = None
    content: str
    source: str = "作者"
    setting_id: str | None = None
    reason: str | None = None
    actor: str = "作者"


class InspirationAddBody(BaseModel):
    content: str
    kind: str = "灵感"
    source: str = ""


class CorpusPathBody(BaseModel):
    """Corpus/feedback file path plus the CLI's ``--apply`` flag."""

    path: str = Field(min_length=1)
    apply: bool = False

    @field_validator("path")
    @classmethod
    def _path_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("path must not be empty or whitespace-only")
        return value


class ConfigWriteBody(BaseModel):
    """One whitelisted config key/value pair for ``PUT /config``."""

    key: str = Field(min_length=1)
    value: Any


def _workspace_dict(workspace: Workspace) -> dict[str, Any]:
    return {field: getattr(workspace, field) for field in _WORKSPACE_FIELDS}


def _agent_dict(agent: Agent) -> dict[str, Any]:
    return {field: getattr(agent, field) for field in _AGENT_FIELDS}


def _iso(value: datetime) -> str:
    """Render a datetime with the same seconds precision the CLI uses."""
    return value.isoformat(timespec="seconds")


def _ascii_slug(value: str) -> str:
    """Keep only ASCII letters/digits, the safe charset for filenames."""
    return "".join(ch for ch in value if ch.isascii() and ch.isalnum())


def _config_snapshot(settings: Settings) -> dict[str, Any]:
    """Full non-sensitive settings snapshot; never includes the LLM key.

    ``data_dir`` / ``config_path`` are exposed as plain strings. The raw
    ``defaults`` table is intentionally excluded: it is a source mirror
    rather than an effective setting and would go stale after a write.
    """
    return {
        "data_dir": str(settings.data_dir),
        "config_path": str(settings.config_path),
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
        "log_level": settings.log_level,
        "quality_threshold": settings.quality_threshold,
        "memory_decay_per_day": settings.memory_decay_per_day,
        "memory_rehearsal_boost": settings.memory_rehearsal_boost,
        "memory_archive_threshold": settings.memory_archive_threshold,
        "proactive_enabled": settings.proactive_enabled,
        "proactive_max_per_agent": settings.proactive_max_per_agent,
        "freedom_dial": settings.freedom_dial,
        "freedom_seed": settings.freedom_seed,
        "motive_llm_enabled": settings.motive_llm_enabled,
        "embedding_backend": settings.embedding_backend,
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "embedding_top_k": settings.embedding_top_k,
        "api_host": settings.api_host,
        "api_port": settings.api_port,
        "panel_poll_interval": settings.panel_poll_interval,
    }


def _event_dict(event: Event) -> dict[str, Any]:
    """Map one event row to its JSON shape (payload parsed like the CLI does)."""
    try:
        payload = json.loads(event.payload or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "id": event.id,
        "workspace_id": event.workspace_id,
        "type": event.type,
        "time": _iso(event.time),
        "actor": event.actor,
        "payload": payload,
    }


def _node_dict(node: WorkspaceStructureNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "kind": node.kind,
        "title": node.title,
        "parent_id": node.parent_id,
        "sort_order": node.sort_order,
        "status": node.status,
        "draft_id": node.draft_id,
        "created_at": _iso(node.created_at),
    }


#: Kind/status label maps mirroring ``cli/structure.py`` so the API accepts the
#: same inputs with the same error text (api must not import cli).
_STRUCTURE_KIND_LABELS: dict[str, str] = {
    structure.KIND_VOLUME: "卷",
    structure.KIND_CHAPTER: "章",
    structure.KIND_SECTION: "篇目",
}
_STRUCTURE_STATUS_LABELS: dict[str, str] = {
    structure.STATUS_WRITING: "创作中",
    structure.STATUS_COMPLETED: "已完成",
    structure.STATUS_SHELVED: "搁置",
}


def _structure_kind_from_label(value: str) -> str:
    """Map a kind input (canonical or Chinese label) to its canonical value."""
    for canonical, label in _STRUCTURE_KIND_LABELS.items():
        if value == canonical or value == label:
            return canonical
    expected = "、".join(_STRUCTURE_KIND_LABELS.values())
    raise NovelError(
        ErrorCode.USAGE_ERROR, f"invalid kind: {value} (expected one of: {expected})"
    )


def _structure_status_from_label(value: str) -> str:
    """Map a status input (canonical or Chinese label) to its canonical value."""
    for canonical, label in _STRUCTURE_STATUS_LABELS.items():
        if value == canonical or value == label:
            return canonical
    expected = "、".join(_STRUCTURE_STATUS_LABELS.values())
    raise NovelError(
        ErrorCode.USAGE_ERROR,
        f"invalid status: {value} (expected one of: {expected})",
    )


def _setting_kind_from_label(value: str) -> str:
    """Map a Chinese kind label back to its canonical kind (like ``setting`` CLI)."""
    for kind, label in setting.KIND_LABELS.items():
        if value == label:
            return kind
    expected = "、".join(setting.KIND_LABELS.values())
    raise NovelError(
        ErrorCode.USAGE_ERROR, f"invalid kind: {value} (expected one of: {expected})"
    )


def _structure_current_parent(
    db: DB, workspace_id: str, node_id: str
) -> str | None:
    """Return a node's current parent id (None means the root level)."""
    with db.workspace_session(workspace_id) as session:
        node = (
            session.query(WorkspaceStructureNode)
            .filter_by(workspace_id=workspace_id, id=node_id)
            .first()
        )
    if node is None:
        raise NovelError(ErrorCode.NOT_FOUND, f"structure node not found: {node_id}")
    return node.parent_id


def _outline_dict(outline_row: Outline) -> dict[str, Any]:
    return {
        "id": outline_row.id,
        "workspace_id": outline_row.workspace_id,
        "version": outline_row.version,
        "content": outline_row.content,
        "reason": outline_row.reason,
        "actor": outline_row.actor,
        "created_at": _iso(outline_row.created_at),
    }


def _setting_dict(entry: SettingEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "kind": entry.kind,
        "name": entry.name,
        "content": entry.content,
        "source": entry.source,
        "current_version": entry.current_version,
        "created_at": _iso(entry.created_at),
        "updated_at": _iso(entry.updated_at),
    }


def _inspiration_dict(row: Inspiration) -> dict[str, Any]:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "kind": row.kind,
        "content": row.content,
        "source": row.source,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _payload_dict(raw: str | None) -> dict:
    """Parse a stored JSON payload, tolerating malformed rows like the CLI."""
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _message_dict(message: Message) -> dict[str, Any]:
    return {
        "id": message.id,
        "role": message.role,
        "actor": message.actor,
        "content": message.content,
        "payload": _payload_dict(message.payload),
        "created_at": _iso(message.created_at),
    }


def _draft_summary(draft_row: Draft) -> dict[str, Any]:
    return {
        "id": draft_row.id,
        "title": draft_row.title,
        "status": draft_row.status,
        "current_version": draft_row.current_version,
        "updated_at": _iso(draft_row.updated_at),
    }


def _draft_write_response(draft_row: Draft) -> dict[str, Any]:
    return {**_draft_summary(draft_row), "awaiting_decision": draft_row.status == "draft"}


def _list_draft_versions(db: DB, workspace_id: str, draft_id: str) -> list[DraftVersion]:
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(DraftVersion)
            .filter_by(draft_id=draft_id)
            .order_by(DraftVersion.version)
            .all()
        )


def _content_excerpt(content: str, limit: int = 20) -> str:
    """Flatten the opening of draft content into one short, assertable line."""
    return " ".join(content.split())[:limit]


def _resolve_writer_option(
    db: DB, workspace_id: str, writer: str | None
) -> Agent | None:
    """Resolve the ``writer`` body field, or None when the default writer is wanted."""
    if writer is None:
        return None
    agent = resolve_agent(db, workspace_id, writer)
    if agent.role != AgentRole.WRITER:
        raise NovelError(ErrorCode.USAGE_ERROR, f"{agent.name} is not a writer")
    return agent


def _revision_is_rebuttal(db: DB, workspace_id: str, draft_id: str) -> bool:
    """True when the revision round already emits the writer rebuttal message."""
    return any(
        item.role == "agent"
        for item in review.list_reviews(db, workspace_id, draft_id)
    )


def _has_style_anchor(db: DB, workspace_id: str) -> bool:
    """True when the workspace has a meaningful style anchor (non-empty description)."""
    with db.workspace_session(workspace_id) as session:
        anchor = session.query(StyleAnchor).filter_by(workspace_id=workspace_id).first()
        return bool(anchor and anchor.description)


def _record_proactive_safe(
    db: DB, workspace_id: str, trigger: str, context: dict
) -> None:
    """Evaluate and persist proactive messages; a failure never rolls business back."""
    try:
        proactive.record_proactive_messages(db, workspace_id, trigger, context)
    except Exception as exc:  # noqa: BLE001 - proactive is post-hoc and optional
        print(f"warning: proactive messages skipped: {exc}", file=sys.stderr)


#: Talk-list marks mirroring ``cli/talk.py`` rendering so the API stays
#: byte-for-byte aligned with ``talk list`` output.
_DISAGREEMENT_MARKS: dict[str, str] = {
    "refusal": "拒绝",
    "rebuttal": "反驳",
    "override": "推翻",
}

_COLLABORATION_MARKS: dict[str, str] = {
    "delegation": "委托",
    "delegation_response": "回应",
}

_DISCUSSION_MARKS: dict[str, tuple[str, str]] = {
    "discussion_open": ("author", "开场"),
    "discussion_contribution": ("agent", "发言"),
    "discussion_summary": ("agent", "总结"),
    "discussion_decision": ("author", "拍板"),
}


def _proactive_kind(payload: dict) -> str | None:
    if payload.get("initiator") != proactive.INITIATOR_AGENT:
        return None
    kind = payload.get("kind")
    return kind if isinstance(kind, str) and kind in proactive.PROACTIVE_KINDS else None


def _discussion_mark(payload: dict) -> tuple[str, str] | None:
    kind = payload.get("kind")
    if not isinstance(kind, str):
        return None
    return _DISCUSSION_MARKS.get(kind)


def _disagreement_mark(payload: dict) -> str | None:
    kind = payload.get("kind")
    if not isinstance(kind, str):
        return None
    return _DISAGREEMENT_MARKS.get(kind)


def _collaboration_mark(payload: dict) -> str | None:
    kind = payload.get("kind")
    if not isinstance(kind, str):
        return None
    return _COLLABORATION_MARKS.get(kind)


def _talk_mark(message: Message) -> str | None:
    """Return the bracket label used by ``talk list`` for one message, if any."""
    payload = _payload_dict(message.payload)
    kind = _proactive_kind(payload)
    if kind is not None:
        return f"agent·主动·{kind}"
    discussion = _discussion_mark(payload)
    if discussion is not None:
        role, mark = discussion
        return f"{role}·讨论·{mark}"
    mark = _disagreement_mark(payload)
    if mark is not None and message.role == "agent":
        return f"agent·分歧·{mark}"
    mark = _collaboration_mark(payload)
    if mark is not None and message.role == "agent":
        return f"agent·互委·{mark}"
    return None


def _talk_dict(message: Message) -> dict[str, Any]:
    """One conversation item aligned with ``talk list`` output."""
    data = _message_dict(message)
    mark = _talk_mark(message)
    data["mark"] = mark
    prefix = f"[{mark}]" if mark is not None else f"[{message.role}]"
    data["line"] = f"{prefix} {message.actor}: {message.content}"
    return data


def _send_talk_message(
    db: DB, workspace_id: str, message: str, settings: Settings
) -> list[dict[str, Any]]:
    """Mirror ``talk send`` using the same core calls; return the new messages."""
    workspace = get_workspace_or_raise(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        before_ids = {
            row.id
            for row in session.query(Message).filter_by(workspace_id=workspace_id).all()
        }

    target_role = resolve_target_role(message)
    agent = get_agent(db, workspace_id, target_role)
    rule = check_refusal(agent, message)
    if rule is not None and is_author_override(message):
        record_message(
            db, workspace_id, role="author", actor=AUTHOR_ACTOR, content=message
        )
        content = rule.acceptance
        payload = {"kind": "override", "stance": rule.stance, "rule": rule.rule}
        record_message(
            db,
            workspace_id,
            role="agent",
            actor=agent.name,
            content=content,
            payload=payload,
        )
        update_agent_mood(db, workspace_id, agent, MOOD_ACCEPTED)
        record_behavior_entry_safe(
            db,
            workspace_id,
            agent_id=agent.id,
            kind="viewpoint",
            target=rule.rule,
            summary="作者推翻后调整",
            before_value="坚持该立场",
            after_value="按作者决定执行",
            source=f"override:{rule.rule}",
        )
        record_behavior_entry_safe(
            db,
            workspace_id,
            agent_id=agent.id,
            kind="relationship",
            target=AUTHOR_ACTOR,
            summary="作者拍板优先",
            source=f"override:{rule.rule}",
        )
        check_summon_trigger_safe(
            db, workspace_id, agent_id=agent.id, target=rule.rule
        )
    elif rule is not None and not has_same_rule_override(
        db, workspace_id, agent, rule.rule
    ):
        record_message(
            db, workspace_id, role="author", actor=AUTHOR_ACTOR, content=message
        )
        repeated = has_same_rule_refusal(db, workspace_id, agent, rule.rule)
        content = rule.reaffirmation if repeated else rule.refusal
        payload: dict[str, object] = {
            "kind": "refusal",
            "stance": rule.stance,
            "rule": rule.rule,
        }
        if repeated:
            payload["repeated"] = True
        record_message(
            db,
            workspace_id,
            role="agent",
            actor=agent.name,
            content=content,
            payload=payload,
        )
        update_agent_mood(db, workspace_id, agent, MOOD_TALK)
        if not repeated:
            record_behavior_entry_safe(
                db,
                workspace_id,
                agent_id=agent.id,
                kind="viewpoint",
                target=rule.rule,
                summary="拒绝了违背立场的指令",
                after_value="坚持该立场",
                source=f"refusal:{rule.rule}",
            )
    else:
        history = list_messages(db, workspace_id)
        client = build_client(settings)
        prompt = build_agent_prompt(
            workspace,
            agent,
            history,
            latest_message=message,
            db=db,
            workspace_id=workspace_id,
        )
        reply = client.complete([LLMMessage(role="user", content=prompt)]).content
        record_message(
            db, workspace_id, role="author", actor=AUTHOR_ACTOR, content=message
        )
        record_message(
            db, workspace_id, role="agent", actor=agent.name, content=reply
        )
        update_agent_mood(db, workspace_id, agent, MOOD_TALK)

        if not has_proactive_message(db, workspace_id):
            editor = get_agent(db, workspace_id, AgentRole.EDITOR)
            record_message(
                db,
                workspace_id,
                role="agent",
                actor=editor.name,
                content=PROACTIVE_QUESTION,
                payload=PROACTIVE_PAYLOAD,
            )
            _record_proactive_safe(
                db,
                workspace_id,
                proactive.TRIGGER_TALK_FIRST_ROUND,
                {
                    "first_round": True,
                    "has_style_anchor": _has_style_anchor(db, workspace_id),
                },
            )

    with db.workspace_session(workspace_id) as session:
        rows = (
            session.query(Message)
            .filter_by(workspace_id=workspace_id)
            .order_by(Message.created_at)
            .all()
        )
    return [_message_dict(row) for row in rows if row.id not in before_ids]


async def _event_stream(
    db: DB, workspace_id: str, after_rowid: int | None
) -> AsyncIterator[dict[str, Any]]:
    """Yield workspace events strictly after the cursor, then poll for new ones."""
    cursor = after_rowid
    while True:
        # Run the synchronous store query in a worker thread so the uvicorn
        # event loop and sse-starlette heartbeats never block on SQLite.
        records = await asyncio.to_thread(
            list_events_since, db, workspace_id, after_rowid=cursor
        )
        for record in records:
            yield {
                "id": str(record.rowid),
                "event": "message",
                "data": json.dumps(_event_dict(record.event), ensure_ascii=False),
            }
            cursor = record.rowid
        await asyncio.sleep(SSE_POLL_SECONDS)


def _overview_dict(item: overview.WorkspaceOverview) -> dict[str, Any]:
    return {
        "workspace_id": item.workspace_id,
        "title": item.title,
        "genre": item.genre,
        "status": item.status,
        "pending_count": item.pending_count,
        "structure": item.structure,
        "last_activity": _iso(item.last_activity),
        "created_at": _iso(item.created_at),
    }


def _style_anchor_dict(db: DB, workspace_id: str) -> dict[str, str]:
    """Read a workspace's style anchor without creating a missing row."""
    anchor = find_style_anchor(db, workspace_id)
    if anchor is None:
        return {"description": "", "forbidden_words": ""}
    return {
        "description": anchor.description,
        "forbidden_words": anchor.forbidden_words,
    }


_QUALITY_SIGNAL_LABELS: dict[str, str] = {
    SIGNAL_DIALOGUE: "对话引语",
    SIGNAL_NUMBER_DETAIL: "数字细节",
    SIGNAL_SENSORY: "感官细节",
}
_QUALITY_SIGNAL_ORDER: tuple[str, ...] = (
    SIGNAL_DIALOGUE,
    SIGNAL_NUMBER_DETAIL,
    SIGNAL_SENSORY,
)


def _quality_score(value: float) -> str:
    """Render a score without a trailing .0, matching ``cli/quality.py``."""
    return f"{value:g}"


def _quality_stats(stats: tuple[float, ...]) -> str:
    """Render min / median / p90 / max like the CLI, or n/a when empty."""
    if not stats:
        return "n/a"
    return (
        f"min {_quality_score(stats[0])} median {_quality_score(stats[1])} "
        f"p90 {_quality_score(stats[2])} max {_quality_score(stats[3])}"
    )


def _quality_agreement(agreement: float, total: int) -> str:
    """Render an agreement fraction as percent plus an exact fraction."""
    numerator = round(agreement * total)
    return f"{agreement * 100:.1f}% ({numerator}/{total})"


def _quality_good_sentences(gems: list[GoodSentence]) -> str | None:
    """Render the good-sentences block, or None when there are no gems."""
    if not gems:
        return None
    indexes = "、".join(str(gem.index) for gem in gems)
    labels = [
        _QUALITY_SIGNAL_LABELS[signal]
        for signal in _QUALITY_SIGNAL_ORDER
        if any(signal in gem.signals for gem in gems)
    ]
    lines = [f"good sentences: 句 {indexes}（{'、'.join(labels)}，建议保留）"]
    lines.extend(f"  {gem.index}: {gem.snippet}" for gem in gems)
    return "\n".join(lines)


def _quality_check_text(
    db: DB, workspace_id: str, draft_id: str, settings: Settings
) -> str:
    """Render the ``quality check`` report for one draft, byte-identical."""
    draft_row = draft.get_draft(db, workspace_id, draft_id)
    version = draft.get_draft_version(
        db, workspace_id, draft_id, draft_row.current_version
    )
    anchor = get_style_anchor(db, workspace_id)
    style_keywords = extract_style_keywords(anchor.description)
    report = check_quality(
        version.content,
        threshold=settings.quality_threshold,
        style_keywords=style_keywords,
    )
    lines = [
        f"passed: {report.passed}",
        f"score: {report.score} (threshold {settings.quality_threshold})",
        f"ai word hits: {report.details['ai_word_hits']}",
        f"modifier hits: {report.details['modifier_hits']}",
        f"sentence repetition: {report.details['sentence_repetition']}",
    ]
    if style_keywords:
        consistency = report.details["style_consistency"]
        lines.append(
            f"style hits: {len(report.details['style_hits'])}/{len(style_keywords)} "
            f"(consistency {consistency:.2f})"
        )
    else:
        lines.append("style hits: n/a (no style keywords)")
    return "\n".join(lines)


def _quality_explain_text(db: DB, workspace_id: str, draft_id: str) -> str:
    """Render the ``quality explain`` report, byte-identical to the CLI."""
    draft_row = draft.get_draft(db, workspace_id, draft_id)
    version = draft.get_draft_version(
        db, workspace_id, draft_id, draft_row.current_version
    )
    anchor = get_style_anchor(db, workspace_id)
    style_keywords = extract_style_keywords(anchor.description)
    issues = explain_quality(version.content)
    lines: list[str] = []
    if issues:
        lines.append(f"{draft_row.title} (v{version.version})")
    lines.append(render_explanation(issues))
    summary = style_consistency_summary(version.content, style_keywords)
    if summary is not None:
        lines.append(summary)
    good_block = _quality_good_sentences(find_good_sentences(version.content))
    if good_block is not None:
        lines.append(good_block)
    return "\n".join(lines)


def _quality_calibrate_text(
    settings: Settings, path: str, apply: bool
) -> str:
    """Render ``quality calibrate`` output and honor the apply flag.

    The CLI prints read failures on stderr; this endpoint inlines those
    warning lines at the same position (after ``skipped``, before ``apply``)
    so no diagnostic is lost over HTTP while the report body stays identical.
    """
    report = scan_corpus(path)
    lines = [f"samples: {len(report.samples)}"]
    for sample in report.samples:
        lines.append(
            f"{sample.path}: 字数 {sample.char_count} · AI 词 {sample.ai_word_hits} · "
            f"修饰词 {sample.modifier_hits} · 句式重复 {sample.sentence_repetition} · "
            f"score {sample.score}"
        )
    lines.append(
        f"distribution: min {report.min} median {report.median} p90 {report.p90} "
        f"p95 {report.p95} max {report.max}"
    )
    lines.append(f"suggested threshold: {report.suggested_threshold}")
    if report.skipped > 0:
        lines.append(f"skipped: {report.skipped}")
    for error in report.errors:
        lines.append(f"warning: {error}")
    if apply:
        lines.append(f"apply: quality_threshold = {report.suggested_threshold}")
        set_quality_threshold(settings.config_path, report.suggested_threshold)
        lines.append(f"config updated: {settings.config_path}")
    return "\n".join(lines)


def _quality_feedback_text(
    settings: Settings, path: str, apply: bool
) -> str:
    """Render ``quality feedback`` output and honor the apply flag."""
    samples = load_feedback_samples(path)
    report = analyze_feedback(samples, settings.quality_threshold)
    total = len(report.samples)
    lines = [
        f"samples: {total}",
        f"bad: {report.bad_count} / good: {report.good_count}",
        f"bad scores: {_quality_stats(report.bad_stats)}",
        f"good scores: {_quality_stats(report.good_stats)}",
        "agreement at threshold "
        f"{report.threshold_used}: {_quality_agreement(report.agreement, total)}",
    ]
    if report.suggested_threshold is None:
        lines.append("suggested threshold: n/a (no bad samples)")
    else:
        lines.append(f"suggested threshold: {report.suggested_threshold}")
        if report.suggested_agreement is not None:
            lines.append(
                "agreement at suggested: "
                f"{_quality_agreement(report.suggested_agreement, total)}"
            )
    if apply:
        if report.suggested_threshold is None:
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                "cannot apply a suggested threshold without bad samples",
                context={"path": path},
            )
        lines.append(f"apply: quality_threshold = {report.suggested_threshold}")
        set_quality_threshold(settings.config_path, report.suggested_threshold)
        lines.append(f"config updated: {settings.config_path}")
    return "\n".join(lines)


def _style_learn_text(
    db: DB, workspace_id: str, path: str, apply: bool
) -> str:
    """Render ``style learn`` output; apply writes the style anchor."""
    get_workspace_or_raise(db, workspace_id)
    texts = collect_corpus_texts(path)
    profile = compute_style_profile(texts)
    description = build_suggested_description(profile)
    lines = [
        f"samples: {profile.samples}",
        f"avg sentence length: {profile.avg_sentence_len:.1f} 字",
        f"short sentence ratio: {profile.short_sentence_ratio * 100:.1f}%",
        f"modifier per 1000 chars: {profile.modifier_per_1000:.1f}",
    ]
    if profile.ai_word_hits:
        lines.append(f"ai words in corpus: {'、'.join(profile.ai_word_hits)}")
    lines.append(f"suggested description: {description}")
    if apply:
        lines.append(f"apply: description = {description}")
        anchor = get_style_anchor(db, workspace_id)
        style.set_style_anchor(
            db,
            workspace_id,
            description=description,
            forbidden_words=anchor.forbidden_words,
        )
        lines.append(f"style anchor updated: {workspace_id}")
    return "\n".join(lines)


def _style_drift_text(db: DB, workspace_id: str) -> str:
    """Render the ``style drift`` report, byte-identical to the CLI."""
    get_workspace_or_raise(db, workspace_id)
    report = compute_style_drift(db, workspace_id)

    if not report.chapters and report.skipped == 0:
        return "no chapters"
    lines: list[str] = []
    if len(report.chapters) < 2:
        lines.append(f"chapters: {len(report.chapters)}")
        if report.skipped > 0:
            lines.append(f"skipped chapters: {report.skipped}")
        lines.append("drift: n/a (need at least 2 chapters)")
        return "\n".join(lines)

    forbidden_words = read_forbidden_words(db, workspace_id)
    lines.append(f"chapters: {len(report.chapters)}")
    if report.baseline_title:
        lines.append(f"baseline: {report.baseline_title}")
    if report.skipped > 0:
        lines.append(f"skipped chapters: {report.skipped}")
    for chapter in report.chapters:
        parts = [
            f"len {chapter.avg_sentence_len:.1f}",
            f"short {chapter.short_sentence_ratio * 100:.1f}%",
            f"mod {chapter.modifier_per_1000:.1f}",
            f"ai {chapter.ai_words_per_1000:.1f}",
        ]
        if chapter.style_hits is not None:
            parts.append(f"style {chapter.style_hits}/{chapter.style_total}")
        lines.append(
            f"{chapter.index} {chapter.title}: {' / '.join(parts)} → drift "
            f"{chapter.drift_score}"
        )
    trend = " / ".join(str(chapter.drift_score) for chapter in report.chapters)
    lines.append(f"drift trend: {trend}")
    if report.drifted:
        drifted = "、".join(
            f"{chapter.title}（{chapter.drift_score}）"
            for chapter in report.drifted
        )
        lines.append(f"drifted chapters: {drifted}")
    for chapter in report.chapters:
        if chapter.forbidden_hits <= 0:
            continue
        words = "、".join(forbidden_words)
        lines.append(
            f"forbidden hits: {chapter.title}: {chapter.forbidden_hits}（{words}）"
        )
    lines.append(f"verdict: {report.verdict}")
    return "\n".join(lines)


def _consistency_text(db: DB, workspace_id: str, draft_id: str) -> str:
    """Render the ``consistency check`` report, byte-identical to the CLI."""
    draft_row = draft.get_draft(db, workspace_id, draft_id)
    version = draft.get_draft_version(
        db, workspace_id, draft_id, draft_row.current_version
    )
    report = check_consistency(db, workspace_id, version.content)
    lines = [
        f"settings checked: {report.settings_checked} / "
        f"threads checked: {report.threads_checked}"
    ]
    for name, count in report.character_mentions.items():
        lines.append(f"[人物] {name}：出现 {count} 次")
    if not report.issues:
        lines.append("no consistency issues found")
        return "\n".join(lines)
    for issue in report.issues:
        if issue.kind == "number_conflict":
            lines.append(f"[冲突] {issue.setting_name}：{issue.detail}")
        elif issue.kind == "character_missing":
            lines.append(f"[未提及] {issue.setting_name}：{issue.detail}")
        else:
            lines.append(f"[未提及] 伏笔·{issue.setting_name}：{issue.detail}")
    return "\n".join(lines)


def _agent_names_map(db: DB, workspace_id: str) -> dict[str, str]:
    """Map agent id to name for one workspace (like the motives CLI helper)."""
    with db.workspace_session(workspace_id) as session:
        agents = session.query(Agent).filter_by(workspace_id=workspace_id).all()
    return {agent.id: agent.name for agent in agents}


def _motives_list_text(
    db: DB, workspace_id: str, agent: str | None
) -> str:
    """Render ``motives list`` output, byte-identical to the CLI."""
    get_workspace_or_raise(db, workspace_id)
    agent_id: str | None = None
    agent_name: str | None = None
    if agent is not None:
        resolved = resolve_agent(db, workspace_id, agent)
        agent_id = resolved.id
        agent_name = resolved.name
    motives = list_motives(db, workspace_id, agent_id=agent_id)
    if not motives:
        if agent_name is not None:
            return f"no motives for {agent_name}"
        return "no motives yet"
    names = _agent_names_map(db, workspace_id)
    lines = []
    for motive in motives:
        owner = names.get(motive.agent_id, motive.agent_id)
        touched = motive.last_touched_at.isoformat(timespec="seconds")
        lines.append(
            f"{motive.id} [{owner}] [{motive.kind}] strength={motive.strength} "
            f"source={motive.source} touched={touched} {motive.content}"
        )
    return "\n".join(lines)


def _patience_text(db: DB, workspace_id: str) -> str:
    """Render ``patience show`` output, byte-identical to the CLI."""
    get_workspace_or_raise(db, workspace_id)
    pools = patience_pools(db, workspace_id)
    lines: list[str] = []
    for pool in pools:
        states = pool["states"]
        lines.append(
            f"[{pool['agent_name']}] pool={pool['pool']} "
            f"patience={pool['effective_patience']} consumed={pool['consumption']} "
            f"rejected={states['rejected']} overridden={states['overridden']} "
            f"conflict={states['conflict']}"
        )
        for state in STATE_KEYS:
            for entry in pool["entries"][state]:
                lines.append(
                    f"  {state}: {entry.target}: {entry.summary} "
                    f"(source={entry.source})"
                )
    return "\n".join(lines)


def _behavior_has_change(entry: BehaviorTimeline) -> bool:
    return bool(entry.before_value or entry.after_value)


def _behavior_timeline_line(entry: BehaviorTimeline, agent_name: str) -> str:
    line = (
        f"{entry.created_at.isoformat(timespec='seconds')} [{entry.kind}] "
        f"{agent_name} -> {entry.target}: {entry.summary}"
    )
    if _behavior_has_change(entry):
        line += f" | {entry.before_value or '无'} -> {entry.after_value or '无'}"
    if entry.source:
        line += f" | source={entry.source}"
    return line


def _behavior_resolve_kinds(kinds: list[str] | None) -> list[str] | None:
    """Validate repeated kind filters exactly like ``cli/behavior.py``."""
    if not kinds:
        return None
    resolved = list(dict.fromkeys(kinds))
    for kind in resolved:
        if kind not in BEHAVIOR_KINDS:
            expected = ", ".join(BEHAVIOR_KINDS)
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                f"unknown behavior kind: {kind} (expected one of: {expected})",
            )
    return resolved


def _behavior_resolve_agent_id(
    db: DB, workspace_id: str, target: str
) -> str:
    """Resolve an agent id, mapping NOT_FOUND to the CLI's usage error."""
    try:
        return resolve_agent(db, workspace_id, target).id
    except NovelError as exc:
        if exc.code is ErrorCode.NOT_FOUND:
            raise NovelError(ErrorCode.USAGE_ERROR, f"unknown agent: {target}") from exc
        raise


def _behavior_timeline_text(
    db: DB,
    workspace_id: str,
    *,
    agent: str | None,
    kinds: list[str] | None,
    limit: int,
) -> str:
    """Render ``behavior timeline`` output, byte-identical to the CLI."""
    get_workspace_or_raise(db, workspace_id)
    agent_id = (
        _behavior_resolve_agent_id(db, workspace_id, agent) if agent else None
    )
    resolved_kinds = _behavior_resolve_kinds(kinds)
    entries = list_behavior_timeline(
        db, workspace_id, agent_id=agent_id, kind=resolved_kinds, limit=limit
    )
    if not entries:
        return "no behavior traces yet"
    names = _agent_names_map(db, workspace_id)
    lines = [
        _behavior_timeline_line(entry, names.get(entry.agent_id, entry.agent_id))
        for entry in entries
    ]
    return "\n".join(lines)


def _behavior_show_text(db: DB, workspace_id: str) -> str:
    """Render ``behavior show`` output, byte-identical to the CLI."""
    get_workspace_or_raise(db, workspace_id)
    state = current_behavior_state(db, workspace_id)
    if not state:
        return "no behavior traces yet"
    with db.workspace_session(workspace_id) as session:
        agents = session.query(Agent).order_by(Agent.created_at).all()
    lines: list[str] = []
    printed = False
    for agent in agents:
        entries = [
            entry
            for (agent_id, _kind, _target), entry in state.items()
            if agent_id == agent.id
        ]
        if not entries:
            continue
        printed = True
        lines.append(f"[{agent.name}]")
        for entry in sorted(entries, key=lambda item: (item.kind, item.target)):
            line = f"  {entry.kind} -> {entry.target}: {entry.summary}"
            if _behavior_has_change(entry):
                line += f"（{entry.before_value or '无'} -> {entry.after_value or '无'}）"
            lines.append(line)
    if not printed:
        return "no behavior traces yet"
    return "\n".join(lines)


def _frontend_dist_dir() -> Path:
    """Frontend build directory: NOVEL_FRONTEND_DIST override, else repo frontend/dist."""
    raw = os.environ.get("NOVEL_FRONTEND_DIST")
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[3] / "frontend" / "dist"


_CREATED_JSON_RESPONSE: dict[str, Any] = {
    "description": "Created",
    "content": {
        "application/json": {
            "schema": {"type": "object", "additionalProperties": True}
        }
    },
}


def create_app() -> FastAPI:
    """Build the FastAPI application bound to the current configuration."""
    settings = load_settings()
    db = DB(settings)
    db.init_schema()

    app = FastAPI(title="Novel Editorial API")

    @app.exception_handler(NovelError)
    async def novel_error_handler(request: Request, exc: NovelError) -> JSONResponse:
        status_code = {
            ErrorCode.NOT_FOUND: 404,
            ErrorCode.USAGE_ERROR: 422,
        }.get(exc.code, 500)
        return JSONResponse(status_code=status_code, content={"detail": exc.message})

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/config")
    def get_config() -> dict[str, Any]:
        """Full non-sensitive settings snapshot consumed by the frontend."""
        current = load_settings()
        return {**_config_snapshot(current), "restart_required": False}

    @app.put("/config")
    def update_config_route(body: ConfigWriteBody) -> dict[str, Any]:
        """Write one whitelisted config key; restart the API server to apply."""
        set_config_value(settings.config_path, body.key, body.value)
        current = load_settings()
        return {
            **_config_snapshot(current),
            "restart_required": True,
            "message": "config updated; api 重启后生效",
        }

    @app.get("/works")
    def list_works() -> list[dict[str, Any]]:
        with db.global_session() as session:
            workspaces = (
                session.query(Workspace)
                .order_by(Workspace.created_at, Workspace.id)
                .all()
            )
        return [_workspace_dict(workspace) for workspace in workspaces]

    @app.post("/works", status_code=201)
    def create_workspace_route(body: CreateWorkspaceBody) -> dict[str, Any]:
        created = workspace.create_workspace(
            db,
            title=body.title,
            genre=body.genre,
            description=body.description,
        )
        return _workspace_dict(created)

    @app.post("/works/import", status_code=201)
    async def import_workspace_route(
        file: Annotated[UploadFile, File()],
    ) -> dict[str, Any]:
        """Import an exported workspace ZIP as a brand-new workspace.

        Mirrors ``works import``: the archive is validated by core.archive and
        always lands under a fresh workspace id (never overwrites). Invalid
        archives surface the NovelError through the shared exception handler.
        """
        fd, tmp_name = tempfile.mkstemp(prefix="novel-api-import-", suffix=".zip")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as raw:
                while chunk := await file.read(1024 * 1024):
                    raw.write(chunk)
            workspace_row = import_workspace_archive(db, tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        return _workspace_dict(workspace_row)

    @app.get("/works/{workspace_id}")
    def show_workspace(workspace_id: str) -> dict[str, Any]:
        with db.global_session() as session:
            found = session.get(Workspace, workspace_id)
            if found is None:
                raise NovelError(
                    ErrorCode.NOT_FOUND,
                    f"workspace not found: {workspace_id}",
                )
            result = _workspace_dict(found)
        with db.workspace_session(workspace_id) as session:
            agents = session.query(Agent).order_by(Agent.created_at, Agent.id).all()
        result["band"] = [_agent_dict(agent) for agent in agents]
        return result

    @app.get("/works/{workspace_id}/export")
    def export_workspace_route(workspace_id: str) -> FileResponse:
        """Download one workspace as a verifiable ZIP archive.

        Mirrors ``works export`` into a fresh temporary directory; the temp
        dir is removed after the response is sent, or on any failure.
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="novel-api-export-"))
        try:
            archive_path = export_workspace_archive(db, workspace_id, tmp_dir)
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{_ascii_slug(workspace_id)[:8]}-{stamp}.zip"
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=filename,
            background=BackgroundTask(shutil.rmtree, tmp_dir, ignore_errors=True),
        )

    @app.get("/overview")
    def get_overview() -> dict[str, Any]:
        """Cross-workspace aggregate, mirroring ``works overview``."""
        report = overview.build_overview(db)
        return {
            "overviews": [_overview_dict(item) for item in report.overviews],
            "total": report.total,
            "skipped": report.skipped,
        }

    @app.get("/events")
    def get_global_events(limit: int = Query(50, ge=1)) -> dict[str, Any]:
        """Newest-first events merged across every workspace.

        The global workspaces registry (workspaces table) is the source of
        truth, matching ``works list`` and ``GET /overview``; no disk scan is
        used. Each workspace stream comes from ``list_events`` in
        rowid-descending order; the merged stream sorts by event time, which
        the store keeps strictly increasing per process, so it equals
        cross-workspace insertion order (rowid itself is per-database and not
        comparable). A workspace whose stream cannot be read is warned about
        on stderr and counted in ``skipped``; the rest still merge.
        """
        merged: list[Event] = []
        skipped = 0
        with db.global_session() as session:
            workspace_ids = [
                row.id
                for row in session.query(Workspace)
                .order_by(Workspace.created_at, Workspace.id)
                .all()
            ]
        for workspace_id in workspace_ids:
            try:
                merged.extend(list_events(db, workspace_id, limit=limit))
            except Exception as exc:  # noqa: BLE001 - per-workspace isolation
                print(
                    f"warning: events skipped: {workspace_id}: {exc}",
                    file=sys.stderr,
                )
                skipped += 1
        merged.sort(key=lambda event: event.time, reverse=True)
        return {
            "events": [_event_dict(event) for event in merged[:limit]],
            "skipped": skipped,
        }

    @app.get("/works/{workspace_id}/pending")
    def get_pending_drafts(workspace_id: str) -> list[dict[str, Any]]:
        """Drafts awaiting the author's decision (like ``decision pending``)."""
        get_workspace_or_raise(db, workspace_id)
        return [
            _draft_summary(draft_row)
            for draft_row in draft.list_pending_drafts(db, workspace_id)
        ]

    @app.post("/works/{workspace_id}/decisions", status_code=201)
    def create_decision(workspace_id: str, body: DecisionBody) -> dict[str, str]:
        """Accept / reject / note one draft: the panel's only write action."""
        get_workspace_or_raise(db, workspace_id)
        updated = decision.decide(
            db,
            workspace_id,
            body.draft_id,
            action=body.action,
            content=body.content,
        )
        return {"id": updated.id, "status": updated.status}

    @app.get("/works/{workspace_id}/inspect")
    def inspect_workspace(
        workspace_id: str, keyword: str | None = None
    ) -> PlainTextResponse:
        """Search every workspace layer; same text the ``inspect`` CLI renders."""
        if keyword is None or not keyword.strip():
            raise NovelError(ErrorCode.USAGE_ERROR, "search keyword must not be empty")
        return PlainTextResponse(
            views.search_all_layers(db, workspace_id, keyword),
            media_type="text/plain",
        )

    @app.get("/works/{workspace_id}/drafts")
    def get_drafts(workspace_id: str) -> list[dict[str, Any]]:
        """Draft list for one workspace (like ``draft list``)."""
        get_workspace_or_raise(db, workspace_id)
        return [
            _draft_summary(draft_row)
            for draft_row in draft.list_drafts(db, workspace_id)
        ]

    @app.get("/works/{workspace_id}/drafts/{draft_id}")
    def get_draft_detail(workspace_id: str, draft_id: str) -> dict[str, Any]:
        """One draft with its full version history."""
        get_workspace_or_raise(db, workspace_id)
        found = draft.get_draft(db, workspace_id, draft_id)
        return {
            "id": found.id,
            "title": found.title,
            "status": found.status,
            "current_version": found.current_version,
            "created_at": _iso(found.created_at),
            "updated_at": _iso(found.updated_at),
            "versions": [
                {
                    "version": version.version,
                    "reason": version.reason,
                    "actor": version.actor,
                    "created_at": _iso(version.created_at),
                    "content": version.content,
                }
                for version in _list_draft_versions(db, workspace_id, draft_id)
            ],
        }

    @app.get(
        "/works/{workspace_id}/drafts/{draft_id}/diff",
        response_class=PlainTextResponse,
    )
    def get_draft_diff(
        workspace_id: str,
        draft_id: str,
        version_a: int = Query(...),
        version_b: int = Query(...),
    ) -> PlainTextResponse:
        """Unified diff between two draft versions (like ``draft diff``).

        Mirrors the CLI semantics: a v0 draft with no versions is a usage
        error, a missing version is not found, and identical versions render
        as ``no differences``.
        """
        get_workspace_or_raise(db, workspace_id)
        draft_row = draft.get_draft(db, workspace_id, draft_id)
        if draft_row.current_version == 0:
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                "cannot diff a draft with no versions; save a version first",
            )
        first = draft.get_draft_version(db, workspace_id, draft_id, version_a)
        second = draft.get_draft_version(db, workspace_id, draft_id, version_b)
        output = draft.diff_versions(first, second)
        return PlainTextResponse(
            output if output else "no differences",
            media_type="text/plain",
        )

    @app.get(
        "/works/{workspace_id}/drafts/{draft_id}/quality/check",
        response_class=PlainTextResponse,
    )
    def get_draft_quality_check(
        workspace_id: str, draft_id: str
    ) -> PlainTextResponse:
        """AI-flavor quality gate report, same text as ``quality check``."""
        get_workspace_or_raise(db, workspace_id)
        return PlainTextResponse(
            _quality_check_text(db, workspace_id, draft_id, settings),
            media_type="text/plain",
        )

    @app.get(
        "/works/{workspace_id}/drafts/{draft_id}/quality/explain",
        response_class=PlainTextResponse,
    )
    def get_draft_quality_explain(
        workspace_id: str, draft_id: str
    ) -> PlainTextResponse:
        """AI-flavor localization + rewrite suggestions, same text as ``quality explain``."""
        get_workspace_or_raise(db, workspace_id)
        return PlainTextResponse(
            _quality_explain_text(db, workspace_id, draft_id),
            media_type="text/plain",
        )

    @app.get(
        "/works/{workspace_id}/drafts/{draft_id}/consistency",
        response_class=PlainTextResponse,
    )
    def get_draft_consistency(
        workspace_id: str, draft_id: str
    ) -> PlainTextResponse:
        """Contradiction report against settings/threads, same text as ``consistency check``."""
        get_workspace_or_raise(db, workspace_id)
        return PlainTextResponse(
            _consistency_text(db, workspace_id, draft_id),
            media_type="text/plain",
        )

    @app.get("/works/{workspace_id}/reviews")
    def get_reviews(
        workspace_id: str, draft_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Review comments on one draft (like ``review list``)."""
        get_workspace_or_raise(db, workspace_id)
        if not draft_id:
            raise NovelError(ErrorCode.USAGE_ERROR, "draft_id is required")
        draft.get_draft(db, workspace_id, draft_id)
        return [
            {
                "id": review_row.id,
                "role": review_row.role,
                "actor": review_row.actor,
                "content": review_row.content,
                "created_at": _iso(review_row.created_at),
            }
            for review_row in review.list_reviews(db, workspace_id, draft_id)
        ]

    @app.get("/works/{workspace_id}/log")
    def get_workspace_log(workspace_id: str) -> PlainTextResponse:
        """Full workflow log text, same source as the ``log`` CLI command."""
        return PlainTextResponse(
            log.build_workspace_log(db, workspace_id),
            media_type="text/plain",
        )

    @app.get("/works/{workspace_id}/events")
    def get_workspace_events(workspace_id: str) -> list[dict[str, Any]]:
        """Latest events for one workspace (newest first, like ``events list``)."""
        get_workspace_or_raise(db, workspace_id)
        return [_event_dict(event) for event in list_events(db, workspace_id)]

    @app.get("/works/{workspace_id}/events/stream")
    def stream_workspace_events(
        workspace_id: str, request: Request
    ) -> EventSourceResponse:
        """SSE stream of workspace events (stateless, resumable by Last-Event-ID).

        The event JSON reuses the store.events contract; the SSE ``id`` is the
        workspace event rowid and only events strictly greater than the cursor
        are pushed, so a reconnecting EventSource never misses or duplicates
        an event. The server keeps no subscription table; heartbeats are
        comment lines and reconnects are handled by the EventSource client.
        """
        get_workspace_or_raise(db, workspace_id)
        raw = request.headers.get("last-event-id")
        after_rowid = int(raw) if raw and raw.isdigit() else None
        return EventSourceResponse(
            _event_stream(db, workspace_id, after_rowid),
            ping=SSE_HEARTBEAT_SECONDS,
        )

    @app.post(
        "/quality/calibrate",
        response_class=PlainTextResponse,
    )
    def calibrate_quality_threshold(
        body: CorpusPathBody,
    ) -> PlainTextResponse:
        """Corpus calibration report; ``apply`` writes config like the CLI."""
        return PlainTextResponse(
            _quality_calibrate_text(settings, body.path, body.apply),
            media_type="text/plain",
        )

    @app.post(
        "/quality/feedback",
        response_class=PlainTextResponse,
    )
    def analyze_quality_feedback(
        body: CorpusPathBody,
    ) -> PlainTextResponse:
        """Trial-reader feedback alignment report; ``apply`` writes config."""
        return PlainTextResponse(
            _quality_feedback_text(settings, body.path, body.apply),
            media_type="text/plain",
        )

    @app.get("/templates")
    def list_band_templates() -> list[dict[str, str]]:
        """Preset editorial band templates in fixed order (like ``works templates``)."""
        return [
            {"name": template.name, "description": template.description}
            for template in templates.list_templates()
        ]

    @app.post("/works/{workspace_id}/talk", status_code=201)
    def send_talk_message(workspace_id: str, body: TalkSendBody) -> dict[str, Any]:
        """Send one message to the band; the addressed partner replies (``talk send``)."""
        messages = _send_talk_message(db, workspace_id, body.message, settings)
        return {"messages": messages}

    @app.get("/works/{workspace_id}/talk")
    def get_workspace_talk(workspace_id: str) -> list[dict[str, Any]]:
        """Conversation for one workspace, marked and rendered like ``talk list``."""
        get_workspace_or_raise(db, workspace_id)
        return [_talk_dict(message) for message in list_messages(db, workspace_id)]

    @app.post("/works/{workspace_id}/drafts", status_code=201)
    def create_draft_route(workspace_id: str, body: DraftGenerateBody) -> dict[str, Any]:
        """Generate a draft version (writer + memory pack + LLM + quality gate)."""
        get_workspace_or_raise(db, workspace_id)
        client = build_client(settings)
        writer_agent = _resolve_writer_option(db, workspace_id, body.writer)
        draft_row = draft.generate_draft(
            db,
            workspace_id,
            title=body.title,
            client=client,
            quality_threshold=settings.quality_threshold,
            writer=writer_agent,
        )
        version = draft.get_draft_version(
            db, workspace_id, draft_row.id, draft_row.current_version
        )
        context = {
            "title": draft_row.title,
            "excerpt": _content_excerpt(version.content),
            "passed": draft_row.status == "draft",
            "current_version": draft_row.current_version,
            "reason": version.reason,
            "agent_id": draft_row.writer_id,
        }
        _record_proactive_safe(
            db, workspace_id, proactive.TRIGGER_DRAFT_GENERATED, context
        )
        if draft_row.status == "draft":
            _record_proactive_safe(
                db, workspace_id, proactive.TRIGGER_DRAFT_GATE_PASSED, context
            )
        return _draft_write_response(draft_row)

    @app.post("/works/{workspace_id}/drafts/new", status_code=201)
    def create_author_draft_route(
        workspace_id: str, body: DraftNewBody
    ) -> dict[str, Any]:
        """Create an empty author-owned draft (no LLM, like ``draft new``)."""
        get_workspace_or_raise(db, workspace_id)
        draft_row = draft.create_author_draft(db, workspace_id, title=body.title)
        return _draft_write_response(draft_row)

    @app.put("/works/{workspace_id}/drafts/{draft_id}/content")
    def save_author_draft_route(
        workspace_id: str, draft_id: str, body: DraftSaveBody
    ) -> dict[str, Any]:
        """Save an author-written version (quality gate, like ``draft save``)."""
        get_workspace_or_raise(db, workspace_id)
        draft_row, _ = draft.save_author_version(
            db,
            workspace_id,
            draft_id,
            content=body.content,
            reason=body.reason,
            quality_threshold=settings.quality_threshold,
        )
        return _draft_write_response(draft_row)

    @app.post("/works/{workspace_id}/drafts/{draft_id}/revise")
    def revise_draft_route(
        workspace_id: str, draft_id: str, body: DraftReviseBody
    ) -> dict[str, Any]:
        """Re-generate a draft as a new version (writer + LLM, like ``draft revise``)."""
        get_workspace_or_raise(db, workspace_id)
        client = build_client(settings)
        writer_agent = _resolve_writer_option(db, workspace_id, body.writer)
        revised = draft.revise_draft(
            db,
            workspace_id,
            draft_id,
            reason=body.reason,
            client=client,
            quality_threshold=settings.quality_threshold,
            writer=writer_agent,
        )
        _record_proactive_safe(
            db,
            workspace_id,
            proactive.TRIGGER_DRAFT_REVISED,
            {
                "rebutted": _revision_is_rebuttal(db, workspace_id, draft_id),
                "passed": revised.status == "draft",
            },
        )
        return _draft_write_response(revised)

    @app.get("/works/{workspace_id}/drafts/{draft_id}/decisions")
    def get_draft_decisions(
        workspace_id: str, draft_id: str
    ) -> list[dict[str, Any]]:
        """Decision records for one draft, oldest first (like ``decision list``)."""
        get_workspace_or_raise(db, workspace_id)
        draft.get_draft(db, workspace_id, draft_id)
        with db.workspace_session(workspace_id) as session:
            rows = (
                session.query(Decision)
                .filter_by(draft_id=draft_id)
                .order_by(Decision.created_at)
                .all()
            )
        return [
            {
                "id": row.id,
                "draft_id": row.draft_id,
                "action": row.action,
                "actor": row.actor,
                "content": row.content,
                "created_at": _iso(row.created_at),
            }
            for row in rows
        ]

    @app.post("/works/{workspace_id}/reviews", status_code=201)
    def create_review_route(workspace_id: str, body: ReviewAddBody) -> dict[str, Any]:
        """Add a review comment to a draft (like ``review add``)."""
        get_workspace_or_raise(db, workspace_id)
        role, actor = review.resolve_reviewer(db, workspace_id, body.source)
        created = review.add_review(
            db,
            workspace_id,
            body.draft_id,
            role=role,
            actor=actor,
            content=body.content,
        )
        return {
            "id": created.id,
            "role": created.role,
            "actor": created.actor,
            "content": created.content,
            "created_at": _iso(created.created_at),
        }

    @app.post("/works/{workspace_id}/style")
    def set_workspace_style_route(workspace_id: str, body: StyleSetBody) -> dict[str, str]:
        """Set the workspace style anchor (like ``style set``)."""
        get_workspace_or_raise(db, workspace_id)
        anchor = style.set_style_anchor(
            db,
            workspace_id,
            description=body.description,
            forbidden_words=body.forbidden,
        )
        _record_proactive_safe(
            db,
            workspace_id,
            proactive.TRIGGER_STYLE_SET,
            {
                "description": anchor.description,
                "forbidden_words": anchor.forbidden_words,
            },
        )
        return {
            "description": anchor.description,
            "forbidden_words": anchor.forbidden_words,
        }

    @app.get("/works/{workspace_id}/style")
    def get_workspace_style(workspace_id: str) -> dict[str, str]:
        """Style anchor for one workspace: description + forbidden words (read-only)."""
        get_workspace_or_raise(db, workspace_id)
        return _style_anchor_dict(db, workspace_id)

    @app.post(
        "/works/{workspace_id}/style/learn",
        response_class=PlainTextResponse,
    )
    def learn_workspace_style(
        workspace_id: str, body: CorpusPathBody
    ) -> PlainTextResponse:
        """Learn a style description from reference texts (like ``style learn``)."""
        return PlainTextResponse(
            _style_learn_text(db, workspace_id, body.path, body.apply),
            media_type="text/plain",
        )

    @app.get(
        "/works/{workspace_id}/style/drift",
        response_class=PlainTextResponse,
    )
    def get_workspace_style_drift(workspace_id: str) -> PlainTextResponse:
        """Cross-chapter style drift report (like ``style drift``)."""
        return PlainTextResponse(
            _style_drift_text(db, workspace_id),
            media_type="text/plain",
        )

    @app.get("/works/{workspace_id}/structure")
    def get_workspace_structure(workspace_id: str) -> list[dict[str, Any]]:
        """Flat, parent-first structure nodes for one workspace."""
        get_workspace_or_raise(db, workspace_id)
        return [_node_dict(node) for node in structure.list_structure(db, workspace_id)]

    @app.post("/works/{workspace_id}/structure", status_code=201)
    def create_structure_node_route(
        workspace_id: str, body: StructureAddBody
    ) -> dict[str, Any]:
        """Add a structure node (volume/chapter/section, like ``structure add``)."""
        get_workspace_or_raise(db, workspace_id)
        node = structure.create_node(
            db,
            workspace_id,
            kind=_structure_kind_from_label(body.kind),
            title=body.title,
            parent_id=body.parent,
            draft_id=body.draft,
            sort_order=body.order,
        )
        return _node_dict(node)

    @app.patch("/works/{workspace_id}/structure/{node_id}")
    def patch_structure_node_route(
        workspace_id: str, node_id: str, body: StructurePatchBody
    ) -> dict[str, Any]:
        """Rename a node or set its status (like ``structure rename/status``)."""
        get_workspace_or_raise(db, workspace_id)
        if body.title is not None and body.status is not None:
            raise NovelError(
                ErrorCode.USAGE_ERROR, "provide exactly one of title or status"
            )
        if body.title is not None:
            node = structure.rename_node(db, workspace_id, node_id, body.title)
        elif body.status is not None:
            node = structure.set_node_status(
                db,
                workspace_id,
                node_id,
                _structure_status_from_label(body.status),
            )
        else:
            raise NovelError(
                ErrorCode.USAGE_ERROR, "provide exactly one of title or status"
            )
        return _node_dict(node)

    @app.post("/works/{workspace_id}/structure/{node_id}/move")
    def move_structure_node_route(
        workspace_id: str, node_id: str, body: StructureMoveBody
    ) -> dict[str, Any]:
        """Move a node under a parent or back to the root (like ``structure move``)."""
        get_workspace_or_raise(db, workspace_id)
        if body.parent is not None and body.root:
            raise NovelError(
                ErrorCode.USAGE_ERROR, "parent and root are mutually exclusive"
            )
        if body.root:
            parent_id = None
        elif body.parent is not None:
            parent_id = body.parent
        elif body.order is not None:
            parent_id = _structure_current_parent(db, workspace_id, node_id)
        else:
            parent_id = None
        node = structure.move_node(
            db, workspace_id, node_id, parent_id=parent_id, sort_order=body.order
        )
        return _node_dict(node)

    @app.delete("/works/{workspace_id}/structure/{node_id}")
    def delete_structure_node_route(
        workspace_id: str, node_id: str
    ) -> dict[str, int]:
        """Remove a node and its whole subtree (like ``structure remove``)."""
        get_workspace_or_raise(db, workspace_id)
        removed = structure.remove_node(db, workspace_id, node_id)
        return {"removed": removed}

    @app.get("/works/{workspace_id}/outline")
    def get_workspace_outline(workspace_id: str) -> dict[str, Any] | None:
        """Current outline version, or null when none (like ``outline show``)."""
        get_workspace_or_raise(db, workspace_id)
        outline_row = outline.get_outline(db, workspace_id)
        return _outline_dict(outline_row) if outline_row is not None else None

    @app.post(
        "/works/{workspace_id}/outline",
        responses={201: _CREATED_JSON_RESPONSE},
    )
    def write_workspace_outline_route(
        workspace_id: str, body: OutlineWriteBody, response: Response
    ) -> dict[str, Any]:
        """Create the first outline (no reason) or revise it (with reason)."""
        get_workspace_or_raise(db, workspace_id)
        if body.reason is None:
            outline_row = outline.create_outline(
                db, workspace_id, content=body.content, actor=body.actor
            )
            response.status_code = 201
        else:
            outline_row = outline.revise_outline(
                db,
                workspace_id,
                content=body.content,
                reason=body.reason,
                actor=body.actor,
            )
        return _outline_dict(outline_row)

    @app.get("/works/{workspace_id}/settings")
    def get_workspace_settings(
        workspace_id: str, kind: str | None = None
    ) -> list[dict[str, Any]]:
        """Settings list, optionally filtered by kind label (like ``setting list``)."""
        get_workspace_or_raise(db, workspace_id)
        kind_value = _setting_kind_from_label(kind) if kind is not None else None
        return [
            _setting_dict(entry)
            for entry in setting.list_settings(db, workspace_id, kind=kind_value)
        ]

    @app.get(
        "/works/{workspace_id}/settings/check", response_class=PlainTextResponse
    )
    def check_workspace_settings(workspace_id: str) -> PlainTextResponse:
        """Stale/same-name conflict report, same text as ``setting check``."""
        return PlainTextResponse(
            setting.check_settings(db, workspace_id),
            media_type="text/plain",
        )

    @app.get("/works/{workspace_id}/settings/{setting_id}")
    def get_workspace_setting(
        workspace_id: str, setting_id: str
    ) -> dict[str, Any]:
        """One setting with its latest version content (like ``setting show``)."""
        get_workspace_or_raise(db, workspace_id)
        return _setting_dict(setting.get_setting(db, workspace_id, setting_id))

    @app.post(
        "/works/{workspace_id}/settings",
        responses={201: _CREATED_JSON_RESPONSE},
    )
    def write_workspace_setting_route(
        workspace_id: str, body: SettingWriteBody, response: Response
    ) -> dict[str, Any]:
        """Add a setting (no setting_id) or revise one (with setting_id + reason)."""
        get_workspace_or_raise(db, workspace_id)
        if body.setting_id is None:
            if body.kind is None:
                raise NovelError(ErrorCode.USAGE_ERROR, "setting kind is required")
            if body.name is None:
                raise NovelError(ErrorCode.USAGE_ERROR, "setting name is required")
            entry = setting.add_setting(
                db,
                workspace_id,
                kind=_setting_kind_from_label(body.kind),
                name=body.name,
                content=body.content,
                source=body.source,
            )
            response.status_code = 201
        else:
            if body.reason is None:
                raise NovelError(ErrorCode.USAGE_ERROR, "setting reason is required")
            entry = setting.revise_setting(
                db,
                workspace_id,
                body.setting_id,
                content=body.content,
                reason=body.reason,
                actor=body.actor,
            )
        return _setting_dict(entry)

    @app.get("/works/{workspace_id}/inspirations")
    def get_workspace_inspirations(
        workspace_id: str,
        kind: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Inspirations, newest first (like ``inspiration list``)."""
        get_workspace_or_raise(db, workspace_id)
        return [
            _inspiration_dict(row)
            for row in inspiration.list_inspirations(
                db, workspace_id, kind=kind, keyword=keyword
            )
        ]

    @app.get("/works/{workspace_id}/inspirations/{inspiration_id}")
    def get_workspace_inspiration(
        workspace_id: str, inspiration_id: str
    ) -> dict[str, Any]:
        """One inspiration with its source (like ``inspiration show``)."""
        get_workspace_or_raise(db, workspace_id)
        return _inspiration_dict(
            inspiration.get_inspiration(db, workspace_id, inspiration_id)
        )

    @app.post("/works/{workspace_id}/inspirations", status_code=201)
    def create_inspiration_route(
        workspace_id: str, body: InspirationAddBody
    ) -> dict[str, Any]:
        """Add one inspiration snippet (like ``inspiration add``)."""
        get_workspace_or_raise(db, workspace_id)
        row = inspiration.add_inspiration(
            db,
            workspace_id,
            content=body.content,
            kind=body.kind,
            source=body.source,
        )
        return _inspiration_dict(row)

    @app.delete("/works/{workspace_id}/inspirations/{inspiration_id}")
    def delete_inspiration_route(
        workspace_id: str, inspiration_id: str
    ) -> dict[str, str]:
        """Remove one inspiration (like ``inspiration remove``)."""
        get_workspace_or_raise(db, workspace_id)
        removed = inspiration.remove_inspiration(db, workspace_id, inspiration_id)
        return {"id": removed.id, "kind": removed.kind}

    @app.get(
        "/works/{workspace_id}/motives",
        response_class=PlainTextResponse,
    )
    def list_workspace_motives(
        workspace_id: str,
        agent: str | None = Query(None, description="Agent id or alias"),
    ) -> PlainTextResponse:
        """Partner motives with kind/strength/source/last touch (like ``motives list``)."""
        return PlainTextResponse(
            _motives_list_text(db, workspace_id, agent),
            media_type="text/plain",
        )

    @app.delete(
        "/works/{workspace_id}/motives/{motive_id}",
        response_class=PlainTextResponse,
    )
    def drop_workspace_motive(
        workspace_id: str, motive_id: str
    ) -> PlainTextResponse:
        """Drop one motive; appends the author_feedback:drop behavior trace."""
        get_workspace_or_raise(db, workspace_id)
        motive = clear_motive(db, workspace_id, motive_id)
        record_behavior_entry_safe(
            db,
            workspace_id,
            agent_id=motive.agent_id,
            kind="viewpoint",
            target=motive.content,
            summary=f"作者放下动机 [{motive.kind}]",
            source="author_feedback:drop",
        )
        return PlainTextResponse(
            f"dropped motive {motive.id} [{motive.kind}] {motive.content}",
            media_type="text/plain",
        )

    @app.get(
        "/works/{workspace_id}/patience",
        response_class=PlainTextResponse,
    )
    def get_workspace_patience(workspace_id: str) -> PlainTextResponse:
        """Every partner's patience pool and state breakdowns (like ``patience show``)."""
        return PlainTextResponse(
            _patience_text(db, workspace_id),
            media_type="text/plain",
        )

    @app.get(
        "/works/{workspace_id}/behavior/timeline",
        response_class=PlainTextResponse,
    )
    def get_workspace_behavior_timeline(
        workspace_id: str,
        agent: str | None = Query(None, description="Filter by agent alias or id"),
        kind: Annotated[
            list[str] | None,
            Query(description="Repeatable behavior kind"),
        ] = None,
        limit: int = Query(20, ge=1, description="Max entries to show"),
    ) -> PlainTextResponse:
        """Behavior traces oldest first (like ``behavior timeline``)."""
        return PlainTextResponse(
            _behavior_timeline_text(
                db, workspace_id, agent=agent, kinds=kind, limit=limit
            ),
            media_type="text/plain",
        )

    @app.get(
        "/works/{workspace_id}/behavior",
        response_class=PlainTextResponse,
    )
    def get_workspace_behavior_state(workspace_id: str) -> PlainTextResponse:
        """Each partner's current behavior state (like ``behavior show``)."""
        return PlainTextResponse(
            _behavior_show_text(db, workspace_id),
            media_type="text/plain",
        )

    frontend_dist = _frontend_dist_dir()
    if frontend_dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=frontend_dist, html=True),
            name="frontend",
        )

    return app
