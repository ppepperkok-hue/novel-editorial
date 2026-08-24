"""FastAPI application: the HTTP door to the same editorial capabilities as the CLI."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

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
from novel_editorial.core.behavior import record_behavior_entry_safe
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
from novel_editorial.core.config import Settings, load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.natural_discussion import check_summon_trigger_safe
from novel_editorial.core.style import find_style_anchor
from novel_editorial.llm.client import LLMMessage, build_client
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events, list_events_since
from novel_editorial.store.models import (
    Agent,
    AgentRole,
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


def _workspace_dict(workspace: Workspace) -> dict[str, Any]:
    return {field: getattr(workspace, field) for field in _WORKSPACE_FIELDS}


def _agent_dict(agent: Agent) -> dict[str, Any]:
    return {field: getattr(agent, field) for field in _AGENT_FIELDS}


def _iso(value: datetime) -> str:
    """Render a datetime with the same seconds precision the CLI uses."""
    return value.isoformat(timespec="seconds")


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


def _frontend_dist_dir() -> Path:
    """Frontend build directory: NOVEL_FRONTEND_DIST override, else repo frontend/dist."""
    raw = os.environ.get("NOVEL_FRONTEND_DIST")
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[3] / "frontend" / "dist"


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
    def get_config() -> dict[str, int]:
        """Panel configuration consumed by the frontend (read-only)."""
        return {"panel_poll_interval": settings.panel_poll_interval}

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

    @app.post("/works/{workspace_id}/outline")
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

    @app.post("/works/{workspace_id}/settings")
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

    frontend_dist = _frontend_dist_dir()
    if frontend_dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=frontend_dist, html=True),
            name="frontend",
        )

    return app
