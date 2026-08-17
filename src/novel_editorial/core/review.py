"""Review services: comments on drafts from author or agents."""

from __future__ import annotations

from novel_editorial.core.behavior import record_behavior_entry_safe
from novel_editorial.core.chat import ROLE_ALIASES, get_agent
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.events import EventType
from novel_editorial.store.db import DB
from novel_editorial.store.events import record_event_in_session
from novel_editorial.store.models import AgentRole, Draft, Review

AUTHOR_ALIASES = ("作者", "author")

REVIEWER_IMPRESSION = {
    "审稿": "盯逻辑与一致性",
    "责编": "盯节奏与钩子",
    "总编": "盯整体结构与基调",
}


def resolve_reviewer(db: DB, workspace_id: str, alias: str) -> tuple[str, str]:
    """Return (role, actor) for a review comment source."""
    if alias in AUTHOR_ALIASES:
        return "author", "作者"
    role = ROLE_ALIASES.get(alias)
    if role is None:
        raise NovelError(ErrorCode.USAGE_ERROR, f"unknown reviewer alias: {alias}")
    agent = get_agent(db, workspace_id, role)
    return "agent", agent.name


def add_review(
    db: DB,
    workspace_id: str,
    draft_id: str,
    *,
    role: str,
    actor: str,
    content: str,
) -> Review:
    with db.workspace_session(workspace_id) as session:
        draft = session.query(Draft).filter_by(workspace_id=workspace_id, id=draft_id).first()
        if draft is None:
            raise NovelError(ErrorCode.NOT_FOUND, f"draft not found: {draft_id}")
        review = Review(
            workspace_id=workspace_id,
            draft_id=draft_id,
            role=role,
            actor=actor,
            content=content,
        )
        session.add(review)
        if role == "agent":
            session.flush()
            record_event_in_session(
                session,
                workspace_id,
                type=EventType.REVIEW_REJECTED,
                actor=actor,
                payload={
                    "review_id": review.id,
                    "draft_id": draft_id,
                    "actor": actor,
                    "content": content,
                },
            )
        session.commit()
    if role == "agent":
        writer = get_agent(db, workspace_id, AgentRole.WRITER)
        if actor != writer.name:
            record_behavior_entry_safe(
                db,
                workspace_id,
                agent_id=writer.id,
                kind="impression",
                target=actor,
                summary=REVIEWER_IMPRESSION.get(actor, "给过修改意见"),
                source="review:add",
            )
            record_behavior_entry_safe(
                db,
                workspace_id,
                agent_id=writer.id,
                kind="relationship",
                target=actor,
                summary="被退过稿" if "退稿" in content else "被指出问题",
                source="review:add",
            )
    return review


def list_reviews(db: DB, workspace_id: str, draft_id: str) -> list[Review]:
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(Review)
            .filter_by(workspace_id=workspace_id, draft_id=draft_id)
            .order_by(Review.created_at)
            .all()
        )
