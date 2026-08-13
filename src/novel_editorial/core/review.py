"""Review services: comments on drafts from author or agents."""

from __future__ import annotations

from novel_editorial.core.chat import ROLE_ALIASES, get_agent
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.events import EventType
from novel_editorial.store.db import DB
from novel_editorial.store.events import record_event_in_session
from novel_editorial.store.models import Draft, Review

AUTHOR_ALIASES = ("作者", "author")


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
        return review


def list_reviews(db: DB, workspace_id: str, draft_id: str) -> list[Review]:
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(Review)
            .filter_by(workspace_id=workspace_id, draft_id=draft_id)
            .order_by(Review.created_at)
            .all()
        )
