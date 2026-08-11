"""Editorial board overview (S14): one payload for the office view."""

from __future__ import annotations

from datetime import datetime


def build_overview(conn):
    """Aggregate agents, relations, unread mail, actions and today's activity."""
    from novel_pipeline.services import activity as activity_service  # noqa: PLC0415
    from novel_pipeline.services import agents as agents_service  # noqa: PLC0415
    from tools import editorial_state, mailroom  # noqa: PLC0415

    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "agents": agents_service.agents_list(),
        "relations": editorial_state.list_relations(conn).get("items") or [],
        "unread": mailroom.unread_summary(conn).get("agents") or {},
        "actions": activity_service.list_actions(conn, limit=100),
        "today_activity": activity_service.list_activity(conn, day=today, limit=200),
    }
