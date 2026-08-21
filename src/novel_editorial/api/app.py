"""FastAPI application: the HTTP door to the same editorial capabilities as the CLI."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from novel_editorial.core import overview, structure, style, workspace
from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events
from novel_editorial.store.models import Agent, Event, Workspace, WorkspaceStructureNode

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

    @app.get("/works/{workspace_id}/events")
    def get_workspace_events(workspace_id: str) -> list[dict[str, Any]]:
        """Latest events for one workspace (newest first, like ``events list``)."""
        get_workspace_or_raise(db, workspace_id)
        return [_event_dict(event) for event in list_events(db, workspace_id)]

    @app.get("/works/{workspace_id}/style")
    def get_workspace_style(workspace_id: str) -> dict[str, str]:
        """Style anchor for one workspace: description + forbidden words."""
        get_workspace_or_raise(db, workspace_id)
        anchor = style.get_style_anchor(db, workspace_id)
        return {"description": anchor.description, "forbidden_words": anchor.forbidden_words}

    @app.get("/works/{workspace_id}/structure")
    def get_workspace_structure(workspace_id: str) -> list[dict[str, Any]]:
        """Flat, parent-first structure nodes for one workspace."""
        get_workspace_or_raise(db, workspace_id)
        return [_node_dict(node) for node in structure.list_structure(db, workspace_id)]

    return app
