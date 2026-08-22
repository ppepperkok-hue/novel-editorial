"""FastAPI application: the HTTP door to the same editorial capabilities as the CLI."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from novel_editorial.core import decision, draft, log, overview, review, structure, views, workspace
from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events
from novel_editorial.store.models import (
    Agent,
    Draft,
    DraftVersion,
    Event,
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


class CreateWorkspaceBody(BaseModel):
    title: str = Field(min_length=1)
    genre: str = ""
    description: str = ""


class DecisionBody(BaseModel):
    draft_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    content: str = ""


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


def _draft_summary(draft_row: Draft) -> dict[str, Any]:
    return {
        "id": draft_row.id,
        "title": draft_row.title,
        "status": draft_row.status,
        "current_version": draft_row.current_version,
        "updated_at": _iso(draft_row.updated_at),
    }


def _list_draft_versions(db: DB, workspace_id: str, draft_id: str) -> list[DraftVersion]:
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(DraftVersion)
            .filter_by(draft_id=draft_id)
            .order_by(DraftVersion.version)
            .all()
        )


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
    with db.workspace_session(workspace_id) as session:
        anchor = (
            session.query(StyleAnchor)
            .filter_by(workspace_id=workspace_id)
            .first()
        )
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
                    "created_at": _iso(version.created_at),
                    "content": version.content,
                }
                for version in _list_draft_versions(db, workspace_id, draft_id)
            ],
        }

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

    frontend_dist = _frontend_dist_dir()
    if frontend_dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=frontend_dist, html=True),
            name="frontend",
        )

    return app
