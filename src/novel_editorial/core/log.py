"""Workspace log aggregation for reviewing a full workflow."""

from __future__ import annotations

import json

from novel_editorial.core.chat import get_workspace_or_raise, list_messages
from novel_editorial.core.draft import list_drafts
from novel_editorial.store.db import DB
from novel_editorial.store.models import Decision, DraftVersion, Review


def _list_versions(db: DB, workspace_id: str, draft_id: str) -> list[DraftVersion]:
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(DraftVersion)
            .filter_by(draft_id=draft_id)
            .order_by(DraftVersion.version)
            .all()
        )


def build_workspace_log(db: DB, workspace_id: str) -> str:
    workspace = get_workspace_or_raise(db, workspace_id)
    lines = [f"作品：《{workspace.title}》（{workspace.genre}）"]

    messages = list_messages(db, workspace_id)
    conversation: list = []
    mood_changes: list[tuple] = []
    for message in messages:
        try:
            payload = json.loads(message.payload or "{}")
        except json.JSONDecodeError:
            payload = {}
        if payload.get("kind") == "mood_change":
            mood_changes.append((message, payload))
        else:
            conversation.append(message)
    if conversation:
        lines.append("\n== 对话 ==")
        for message in conversation:
            lines.append(f"[{message.role}] {message.actor}: {message.content}")
    if mood_changes:
        lines.append("\n== 状态 ==")
        for message, payload in mood_changes:
            agent = payload.get("agent") or message.actor
            lines.append(f"[{agent}] {payload.get('from')} -> {payload.get('to')} (mood_change)")

    drafts = list_drafts(db, workspace_id)
    if drafts:
        lines.append("\n== 草稿 ==")
        for draft in drafts:
            lines.append(f"{draft.title} ({draft.status}, v{draft.current_version})")
            for version in _list_versions(db, workspace_id, draft.id):
                preview = version.content[:100].replace("\n", " ")
                lines.append(f"  v{version.version} [{version.reason}]: {preview}")

    with db.workspace_session(workspace_id) as session:
        reviews = (
            session.query(Review)
            .filter_by(workspace_id=workspace_id)
            .order_by(Review.created_at)
            .all()
        )
        decisions = (
            session.query(Decision)
            .filter_by(workspace_id=workspace_id)
            .order_by(Decision.created_at)
            .all()
        )
    if reviews:
        lines.append("\n== 意见 ==")
        for review in reviews:
            lines.append(f"[{review.role}] {review.actor}: {review.content}")
    if decisions:
        lines.append("\n== 决策 ==")
        for decision in decisions:
            suffix = f": {decision.content}" if decision.content else ""
            lines.append(f"[{decision.action}] {decision.actor}{suffix}")
    return "\n".join(lines)
